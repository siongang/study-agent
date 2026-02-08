"""Extract exam coverage using LLM (Phase 4)."""
import json
import os
from datetime import datetime, timezone
from typing import Optional

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.models.coverage import ExamCoverage


def extract_coverage(
    full_text: str,
    filename: str,
    file_id: str,
    max_chars: int = 8000
) -> tuple[Optional[ExamCoverage], Optional[str]]:
    """Extract structured exam coverage from exam overview text using LLM."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None, "GOOGLE_API_KEY not found"
    
    client = genai.Client(api_key=api_key)
    
    text_to_analyze = full_text[:max_chars]
    if len(full_text) > max_chars:
        text_to_analyze += "\n[...truncated...]"
    
    prompt = f"""Extract exam coverage from this exam overview.

Return JSON:
{{
  "exam_id": "midterm_1",
  "exam_name": "Midterm Examination 1", 
  "exam_date": "February 27, 2026",
  "chapters": [1, 2, 3],
  "topics": [
    {{"chapter": 1, "chapter_title": "Title", "bullets": ["topic1", "topic2"]}}
  ]
}}

Document:
{text_to_analyze}"""
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
        data["source_file_id"] = file_id
        data["generated_at"] = datetime.now(timezone.utc).isoformat()
        
        coverage = ExamCoverage(**data)
        return coverage, None
        
    except ValidationError as e:
        return None, f"Validation failed: {e}"
    except Exception as e:
        return None, f"Extraction failed: {str(e)}"
