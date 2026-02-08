"""CLI tool to extract table of contents from textbooks (Phase 4.5)."""
import argparse
import logging
import sys
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from dotenv import load_dotenv

from app.tools.toc_extraction import extract_all_textbook_tocs, extract_single_textbook_toc


console = Console()


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Extract table of contents from textbooks"
    )
    parser.add_argument(
        "--file-id",
        type=str,
        help="Process only this file ID (optional)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-extraction even if already extracted"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("storage/state/manifest.json"),
        help="Path to manifest.json"
    )
    parser.add_argument(
        "--extracted-text-dir",
        type=Path,
        default=Path("storage/state/extracted_text"),
        help="Directory with extracted text files"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("storage/state/textbook_metadata"),
        help="Directory to save textbook metadata files"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging (shows detailed extraction process)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (shows AI input/output, very verbose)"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.debug:
        log_level = logging.DEBUG
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    elif args.verbose:
        log_level = logging.INFO
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
    else:
        log_level = logging.WARNING
        log_format = "%(levelname)s - %(message)s"
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging level set to: {logging.getLevelName(log_level)}")
    
    # Single file mode
    if args.file_id:
        result = extract_single_textbook_toc(
            file_id=args.file_id,
            manifest_path=args.manifest,
            extracted_text_dir=args.extracted_text_dir,
            output_dir=args.output_dir
        )
        
        if result:
            console.print(f"\n✓ [green]Success![/green] Processed: {result['filename']}")
            if result['toc_pages']:
                console.print(f"  TOC found on pages: {result['toc_pages']}")
                console.print(f"  Extracted {result['num_chapters']} chapters")
                if result['page_range'][0]:
                    console.print(f"  Page range: {result['page_range'][0]}-{result['page_range'][1]}")
            else:
                console.print(f"  {result['notes']}")
        else:
            console.print("[red]✗ Failed to extract TOC[/red]")
        return
    
    # Batch mode: process all textbooks
    if args.force:
        console.print("\n[bold cyan]Extracting TOC from all textbooks (force mode - re-extracting all)...[/bold cyan]\n")
    else:
        console.print("\n[bold cyan]Extracting TOC from all textbooks...[/bold cyan]\n")
    
    processed_files = []
    
    def progress_callback(file_entry):
        console.print(f"Processing: [yellow]{file_entry.filename}[/yellow]")
        processed_files.append(file_entry)
    
    try:
        stats = extract_all_textbook_tocs(
            manifest_path=args.manifest,
            extracted_text_dir=args.extracted_text_dir,
            output_dir=args.output_dir,
            progress_callback=progress_callback,
            force=args.force
        )
        
        # Display results
        console.print(f"\n[bold green]Extraction Complete![/bold green]\n")
        
        # Create summary table
        table = Table(title="TOC Extraction Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="magenta", justify="right")
        
        table.add_row("Textbooks processed", str(stats["extracted"]))
        table.add_row("Total chapters extracted", str(stats["total_chapters"]))
        table.add_row("Skipped (already done or not textbook)", str(stats["skipped"]))
        table.add_row("Failed", str(stats["failed"]))
        
        console.print(table)
        
        # Show per-file details
        if processed_files:
            console.print("\n[bold]Details:[/bold]")
            for file_entry in processed_files:
                # Load the saved metadata to show details
                metadata_path = args.output_dir / f"{file_entry.file_id}.json"
                if metadata_path.exists():
                    import json
                    metadata = json.loads(metadata_path.read_text())
                    console.print(f"\n  • [yellow]{file_entry.filename}[/yellow]")
                    if metadata['chapters']:
                        console.print(f"    TOC found on pages: {metadata['toc_source_pages']}")
                        console.print(f"    Extracted {len(metadata['chapters'])} chapters")
                        page_starts = [c['page_start'] for c in metadata['chapters']]
                        page_ends = [c['page_end'] for c in metadata['chapters']]
                        console.print(f"    Page range: {min(page_starts)}-{max(page_ends)}")
                    else:
                        console.print(f"    {metadata['notes']}")
        
        if stats["failed"] > 0:
            console.print(f"\n[yellow]⚠ {stats['failed']} file(s) failed to process[/yellow]")
            
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        raise


if __name__ == "__main__":
    main()
