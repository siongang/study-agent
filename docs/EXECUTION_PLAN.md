Below is a **thorough execution plan** broken into phases, and for **each phase** I'm giving you a **Cursor-ready prompt** that includes the exact context/constraints so Cursor doesn't invent architecture or skip steps.

This plan assumes:

* **Google ADK** for agents + tool calling
* **local file-based storage** for uploads + state
* **local RAG** with FAISS for semantic retrieval
* PDFs are the primary inputs (syllabus, exam overviews, textbook chapters)
* We must support **multiple exams** with interleaved study scheduling

---

## System Overview

The system follows a pedagogical RAG approach to generate comprehensive, multi-exam study plans:

1. **Ingest**: Scan uploads → extract text → classify doc types
2. **Scope**: Parse exam coverage from overview PDFs (what to study)
3. **Index**: Chunk textbooks → embed → build FAISS index
4. **Enrich**: RAG Scout finds WHERE each topic is covered (pages, problems, terms)
5. **Plan**: Generate multi-exam interleaved schedule with Socratic questions
6. **Tutor**: Answer questions with evidence citations

**Absolute rules**

* Root agent must **never guess** exam scope.
* If required materials are missing, the system must return a **structured "missing items" response** that the root agent uses to ask the user to upload them.
* Use deterministic checks for readiness/coverage (tool logic), not LLM vibes.
* Only use LLM for: coverage extraction, Socratic question generation, answer synthesis.

**Storage layout**

```
storage/
  uploads/                      # raw user uploads (user-controlled, unstructured)
  state/
    manifest.json               # file inventory + doc types
    extracted_text/             # per file extracted text cache
    textbook_metadata/          # per textbook TOC (chapter boundaries)
    chunks/                     # chunk store (JSONL) with chapter tags
    index/                      # FAISS index + mappings
    embeddings/                 # embedding cache (per chunk_id)
    coverage/                   # per-exam coverage JSON (skeleton)
    enriched_coverage/          # coverage + RAG-sourced pages/problems
    plans/                      # generated study plans
    logs/                       # tool call traces
```

**Packages available**

* google-adk, google-genai, pymupdf, pdfplumber, tiktoken, faiss-cpu, pydantic, tqdm, numpy, python-dotenv, rich

---

# Phase 1 — Manifest (inventory + change detection)

## Deliverable

* `storage/state/manifest.json` created/updated deterministically
* detects new vs changed files by SHA-256
* no PDF parsing yet, no doc types beyond `"unknown"`

## Cursor prompt (Phase 1)

```text
You are implementing Phase 1 ONLY of an ADK-based study agent system.

Goal: implement a deterministic file manifest system that scans `storage/uploads/` and writes `storage/state/manifest.json`.

Requirements:
- Do NOT implement PDF extraction, doc classification, chunking, embeddings, RAG, or ADK agents yet.
- Only inventory + change detection.

Project structure to create:
- app/models/manifest.py (Pydantic models)
- app/tools/fs_scan.py (scan + hash)
- app/tools/manifest_io.py (load/save/update)
- optionally app/cli/update_manifest.py for manual testing

Manifest schema (must match):
Manifest:
- version:int = 1
- last_scan:str (ISO timestamp)
- files:list[ManifestFile]

ManifestFile:
- file_id:str (stable internal id, keep if unchanged)
- path:str (relative path)
- filename:str
- sha256:str
- size_bytes:int
- modified_time:float (unix timestamp)
- doc_type:str default "unknown"
- status:str allowed "new"|"processed"|"stale"|"error"
- derived:list[str] default []

Update logic:
- Scan uploads recursively; include only .pdf
- Compute sha256 per file
- If manifest does not exist: create it and mark all files as status="new"
- If file path not in manifest: add entry status="new"
- If file exists but sha changed: status="stale"
- If unchanged: preserve status (do not set to processed automatically)
- Ignore deleted files for now (do not remove)
- Save atomically (write temp then replace)

Also add a small CLI entry to run:
`python -m app.cli.update_manifest`
which prints a summary (#new, #stale, #unchanged).

Write clean code with comments.
```

---

# Phase 2 — PDF text extraction cache (no chunking yet)

## Deliverable

* Extracted text saved per file in `storage/state/extracted_text/<file_id>.json`
* Uses PyMuPDF primarily; pdfplumber fallback
* Extract first page text and full text

## Cursor prompt (Phase 2)

```text
Implement Phase 2: PDF text extraction + caching.

Context:
We have Phase 1 manifest working. Files are in `storage/uploads/`. Manifest at `storage/state/manifest.json`.

Goal:
For each PDF with status in {"new","stale"}:
- Extract text with PyMuPDF (fitz). If it fails, fallback to pdfplumber.
- Save extracted text JSON at `storage/state/extracted_text/{file_id}.json` containing:
  - file_id
  - path
  - num_pages
  - pages: list of page strings
  - full_text: single concatenated string
  - first_page: pages[0] string (or empty)
  - extracted_at ISO timestamp
- Update manifest entry: append derived artifact path, and set status="processed" ONLY if extraction succeeded.
- If extraction fails, set status="error" and store error message in a new optional field `error` (add to model).

Constraints:
- Do NOT implement doc classification yet.
- Do NOT implement chunking/embeddings/RAG yet.
- Keep extraction deterministic and cached.
- Only re-extract for new/stale files.

Add:
- app/tools/pdf_extract.py
- app/cli/extract_text.py runnable as `python -m app.cli.extract_text` showing progress with tqdm.
Update Pydantic models accordingly (optional error field).
```

---

# Phase 3 — Doc type classification (deterministic rules, no LLM)

## Deliverable

* `doc_type` set to one of: `syllabus`, `exam_overview`, `textbook`, `other`, `unknown`
* confidence score + signals stored in manifest
* still no chunking/embeddings yet

## Cursor prompt (Phase 3)

```text
Implement Phase 3: deterministic document classification.

Context:
We have extracted text cached per file in `storage/state/extracted_text/{file_id}.json`.
We have a manifest tracking files and statuses.

Goal:
Classify each processed file into doc_type:
- "syllabus"
- "exam_overview"
- "textbook"
- "other"
- "unknown"

Rules must be deterministic (NO LLM).
Use first_page and/or full_text keyword heuristics:
Examples:
Syllabus signals: "Course Outline", "Syllabus", "Course description", "Final grade", "Assignments"
Exam overview signals: "Midterm Examination", "Final Examination", "Coverage:", "This examination covers", "Chapter 1:"
Textbook signals: frequent "Chapter", "Section", no dates/grading, long length.

Implementation:
- Create app/tools/doc_classify.py with function:
  classify_document(text_first_page:str, full_text:str, filename:str) -> {doc_type, confidence, signals:list[str]}
- Confidence is 0..1 based on number/strength of matches.
- Update manifest entries with:
  - doc_type
  - doc_confidence
  - doc_signals

Constraints:
- Do NOT hardcode specific course names; make it generic.
- Do NOT implement exam coverage extraction yet.
- Do NOT implement chunking/embeddings/RAG yet.

Add CLI:
`python -m app.cli.classify_docs`
prints each file with doc_type and confidence.
Update manifest models accordingly.
```

---

# Phase 4 — Exam coverage extraction (from exam overview PDFs)

## Deliverable

* For each `exam_overview`, generate `storage/state/coverage/<file_id>.json`
* Extract:
  * exam label/name (midterm_1 if possible, else derived)
  * exam date if present
  * covered chapters list
  * per-chapter topic bullets
* This coverage JSON is **source of truth** for exam scope (the "skeleton")

## Cursor prompt (Phase 4)

```text
Implement Phase 4: extract exam coverage from exam overview documents.

Context:
Manifest now includes doc_type. For doc_type=="exam_overview" we have extracted text cached.
We need structured exam scope to avoid guessing.

Goal:
For each exam_overview:
- Use LLM (google-genai with gemini-2.0-flash) to parse full_text and extract:
  - exam_name (e.g., "Midterm Examination 1" or similar)
  - exam_date if present (best-effort parse; store as raw string if needed)
  - covered chapters list (e.g. "Coverage: Chapters 1,2,3,4,5")
  - structured outline: Chapter headings + bullet topics under each chapter
- Output JSON at `storage/state/coverage/{file_id}.json` with schema:
  {
    "exam_id": "midterm_1" (or deterministic fallback like "exam_<file_id>"),
    "exam_name": "...",
    "exam_date": "...",
    "chapters": [1,2,3,4,5],
    "topics": [
      {"chapter": 1, "chapter_title": "...", "bullets": ["...", "..."]},
      ...
    ],
    "source_file_id": "...",
    "generated_at": "ISO"
  }

Implementation details:
- Create app/tools/coverage_extract.py
- Use structured output with Pydantic models for reliability
- If chapter list cannot be parsed, keep chapters empty but still output topics where possible
- Update manifest derived artifacts list for that file

Add CLI:
`python -m app.cli.extract_coverage`
prints coverage summary (exam_id, chapters, #topics).
```

---

# Phase 4.5 — Textbook TOC extraction (chapter boundaries for filtering)

## Deliverable

* For each **textbook**, extract table of contents to map chapters to page ranges
* Store in `storage/state/textbook_metadata/<file_id>.json`
* This enables chapter-aware chunking and filtering during RAG retrieval
* Critical for improving retrieval precision in Phase 7 (RAG Scout)

## Cursor prompt (Phase 4.5)

```text
Implement Phase 4.5: Extract table of contents from textbooks.

Context:
Manifest includes doc_type. For doc_type=="textbook" we have extracted text cached.
We need chapter-to-page mappings to improve retrieval accuracy later.

Goal:
For each textbook:
- Identify TOC location (usually first 10-30 pages)
- Use LLM (google-genai with gemini-2.0-flash) to extract structured chapter information
- Output JSON at `storage/state/textbook_metadata/{file_id}.json` with schema:
  {
    "file_id": "...",
    "filename": "John D Sterman - Business Dynamics.pdf",
    "doc_type": "textbook",
    "extracted_at": "ISO timestamp",
    "toc_source_pages": [5, 6, 7],  // Which pages the TOC was found on
    "chapters": [
      {
        "chapter": 1,
        "title": "Introduction to System Dynamics",
        "page_start": 1,
        "page_end": 35
      },
      {
        "chapter": 2,
        "title": "System Behavior and Causal Loop Diagrams",
        "page_start": 36,
        "page_end": 89
      }
    ],
    "notes": "TOC extracted successfully from pages 5-7"
  }

Implementation details:
- Create app/models/textbook_metadata.py (Pydantic models: TextbookMetadata, ChapterInfo)
- Create app/tools/toc_extract.py with function:
  extract_toc(file_id: str, pages: list[str], filename: str) -> TextbookMetadata

TOC extraction strategy:
1. Load first 30 pages from extracted_text JSON
2. Search for TOC indicators:
   - Keywords: "Contents", "Table of Contents", "Chapter", "Part"
   - Page number patterns (e.g., "Chapter 1 ............. 15")
3. Call LLM with prompt:
   "Extract the table of contents from this textbook. For each chapter, provide:
   - chapter number (integer)
   - chapter title (string)
   - page_start (integer, where chapter begins)
   - page_end (integer, where chapter ends, infer from next chapter start - 1)
   
   Return as structured JSON array. Handle Roman numerals, multi-part chapters, appendices.
   If TOC spans multiple pages, use all provided pages. If no clear TOC, return empty array."

4. Use structured output with Pydantic for reliability
5. Validate results:
   - Chapters should be sequential
   - Page ranges should not overlap
   - page_start < page_end
   - If validation fails, log warning but save what we have

6. Update manifest entry: append "state/textbook_metadata/{file_id}.json" to derived list

Edge cases:
- No clear TOC found: Save metadata with empty chapters array, set notes="No TOC detected"
- Multi-level TOC (parts/chapters/sections): Extract only chapter level for MVP
- Roman numerals in page numbers: LLM should handle conversion
- Appendices: Include as "chapter" with number like 999 or "A"

Constraints:
- Only process textbooks (doc_type=="textbook")
- Skip if textbook_metadata already exists (check derived list in manifest)
- Do NOT implement chunking yet
- Do NOT implement embeddings/RAG yet

Error handling:
- If LLM extraction fails, save metadata with empty chapters + error note
- Don't block pipeline - chunking can proceed without TOC (just less precise)

Create orchestration function:
- app/tools/toc_extraction.py:
  extract_all_textbook_tocs(manifest_path, extracted_text_dir, output_dir) -> stats

Add CLI:
`python -m app.cli.extract_toc`
prints:
- Processing: Sterman - Business Dynamics.pdf
  * TOC found on pages 5-7
  * Extracted 11 chapters
  * Page range: 1-542
- Processing: Triola - Biostatistics.pdf
  * TOC found on pages 9-12
  * Extracted 14 chapters
  * Page range: 1-789
- Summary: 2 textbooks processed, 25 chapters total

Also support single file:
`python -m app.cli.extract_toc --file-id {file_id}`

Add to manifest models:
- No schema change needed, just append to derived list

Files to create:
- app/models/textbook_metadata.py
- app/tools/toc_extract.py
- app/tools/toc_extraction.py (orchestrator)
- app/cli/extract_toc.py
```

---

# Phase 5 — Chunking (token-based) + chunk store with section detection

## Deliverable

* Chunk all **textbook** docs into chunks with accurate page metadata
* Store as JSONL in `storage/state/chunks/chunks.jsonl`
* Each chunk has stable `chunk_id`, file_id, page range, token count, section_type metadata

## Cursor prompt (Phase 5)

```text
Review and enhance Phase 5: token-based chunking with chapter-aware metadata.

Context:
We have extracted text cached and doc_type classified.
We have textbook TOC metadata from Phase 4.5 (chapter boundaries).
Current chunking.py already implements page-aware chunking.

Task:
1. Verify that page numbers in chunks are 1-indexed and accurate
2. Load textbook TOC metadata (if available) to tag chunks with chapter numbers
3. Add section_type detection to chunk metadata using simple heuristics

Chunk metadata fields to add:
- section_type (one of: "explanation", "problems", "summary", "other")
- chapter_number (integer, optional - from TOC mapping)
- chapter_title (string, optional - from TOC mapping)

Detection rules (deterministic, NO LLM):

A) section_type detection:
- If chunk contains keywords: "Problem", "Exercise", "Practice", "Question" → mark as "problems"
- If chunk contains: "Summary", "Key Points", "Review", "Conclusion" → mark as "summary"
- Default: "explanation"

B) chapter_number detection:
- Load textbook_metadata/{file_id}.json (if exists)
- For each chunk, check if page_start falls within any chapter's page range
- If page_start is between chapter.page_start and chapter.page_end:
  * Set chunk.chapter_number = chapter.chapter
  * Set chunk.chapter_title = chapter.title
- If no TOC metadata or page doesn't match any chapter:
  * Leave chapter_number = null
  * This is OK - chunking still works, just less precise for filtering

Implementation:
- Update app/models/chunks.py to include:
  * section_type: str
  * chapter_number: Optional[int] = None
  * chapter_title: Optional[str] = None

- Update app/tools/chunking.py:
  * Load TOC metadata at start of chunking process
  * For each chunk, look up chapter based on page_start
  * Detect section_type using keywords
  * Store all metadata with chunk

- Store chunks in `storage/state/chunks/chunks.jsonl` (one JSON per line)
- Also maintain `storage/state/chunks/chunk_index.json` mapping:
  chunk_id -> {file_id, page_start, page_end, section_type, chapter_number}

Chunking parameters:
- target 600-900 tokens per chunk
- overlap 100-150 tokens
- use tiktoken for token counting

Chunk ID:
- deterministic: sha1(file_sha256 + ":" + page_start + "-" + page_end + ":" + chunk_index)

Only (re)chunk files that are new/stale or whose chunks are missing.
Update manifest derived artifacts list accordingly.

CLI test:
`python -m app.cli.chunk_textbook`
should print:
- Sterman - Business Dynamics.pdf
  * 542 chunks created
  * Chapter breakdown: Ch1: 45, Ch2: 38, Ch3: 52, ... (if TOC available)
  * Section breakdown: explanation: 480, problems: 45, summary: 17
- Triola - Biostatistics.pdf
  * 678 chunks created
  * No TOC metadata (chunking proceeded without chapter tags)
  * Section breakdown: explanation: 610, problems: 55, summary: 13

Also support single file:
`python -m app.cli.chunk_textbook --file-id {file_id}`

Do NOT implement embeddings yet.
```

---

# Phase 6 — Embeddings + FAISS index with modern SDK

## Deliverable

* Embed chunk texts with `google-genai` (modern SDK) using `text-embedding-004`
* Build FAISS index for semantic retrieval
* Maintain mapping FAISS row → chunk_id
* Simple embedding cache to avoid redundant API calls

## Cursor prompt (Phase 6)

```text
Implement Phase 6: embeddings + FAISS index using modern google-genai SDK.

Context:
Chunks exist in `storage/state/chunks/chunks.jsonl` with page metadata, section_type, and chapter_number.
We want local semantic retrieval over textbook content with chapter-aware filtering.

Goal:
- Embed each chunk text using google-genai (NOT google-generativeai)
- Use text-embedding-004 model
- Build FAISS index and persist it
- Implement simple file-based embedding cache

Files to create:
- `storage/state/index/faiss.index` (FAISS IndexFlatIP for cosine similarity)
- `storage/state/index/row_to_chunk_id.json` (mapping FAISS row index to chunk_id)
- `storage/state/embeddings/{chunk_id}.npy` (one file per chunk embedding)

Implementation:
- app/tools/embed.py:
  * embed_texts(texts: list[str], model="text-embedding-004") -> np.ndarray
  * Use google.genai.types.GenerateEmbeddingConfig
  * Handle batching (max 100 texts per batch recommended)
  * Add retry logic with exponential backoff for rate limits
  
- app/tools/embedding_cache.py:
  * get_or_compute_embedding(chunk_id: str, text: str) -> np.ndarray
  * Check if storage/state/embeddings/{chunk_id}.npy exists
  * If exists, load and return; else compute, save, and return
  * Only re-embed if chunk text changes (detect via hash comparison)

- app/tools/faiss_store.py:
  * build_index(chunks: list[Chunk]) -> saves FAISS index + row mapping
  * search(query_text: str, top_k: int = 10, filters: dict = None) -> list[{chunk_id, score, chunk}]
  * Filters can include: file_id, page_range, section_type, chapter_number (from Phase 4.5 TOC)
  * Implement post-retrieval filtering (retrieve top_k*2, then filter, then return top_k)
  * Use IndexFlatIP (inner product for cosine similarity with normalized vectors)

- app/tools/retrieve.py:
  * retrieve_chunks(question: str, top_k: int = 10, filters: dict = None) -> list[Chunk]
  * Wrapper that combines search + chunk loading

Constraints:
- For MVP, rebuild entire index when any chunk changes is acceptable
- Normalize embeddings before adding to FAISS (for cosine similarity)
- No LLM answering yet—just retrieval API

Add CLI:
`python -m app.cli.build_index`
prints "Embedded X chunks (Y cached, Z new), built FAISS index with D dimensions"

`python -m app.cli.search_chunks "binomial distribution" --top-k 5`
prints: chunk_id, score, file, pages, section_type, snippet (first 100 chars)
```

---

# Phase 7 — RAG Scout: Enrich coverage with textbook evidence

## Deliverable

* For each exam coverage, "scout" the RAG index to find concrete resources
* Generate **Enriched Coverage JSON** with page ranges, practice problems, key terms
* This bridges the gap between abstract learning objectives and concrete textbook content

## Cursor prompt (Phase 7)

```text
Implement Phase 7: RAG Scout - Enrich exam coverage with textbook evidence.

Context:
- We have Coverage JSON with exam_id, chapters, topic bullets (the skeleton)
- We have FAISS index over textbook chunks with page metadata, section_type, and chapter_number
- We have textbook TOC metadata mapping chapters to page ranges (from Phase 4.5)
- Goal: For each topic bullet, find WHERE it's covered (pages, problems, terms)

Deliverable:
Create "Enriched Coverage JSON" at storage/state/enriched_coverage/{file_id}.json

Schema for EnrichedCoverage:
{
  "exam_id": "midterm_1",
  "exam_name": "...",
  "exam_date": "...",
  "source_file_id": "...",
  "enriched_at": "ISO timestamp",
  "topics": [
    {
      "chapter": 1,
      "chapter_title": "...",
      "bullet": "Original bullet text from coverage",
      "reading_pages": {
        "file_id": "...",
        "filename": "Sterman - Business Dynamics.pdf",
        "page_ranges": [[137, 155], [202, 210]]  # Consolidated ranges
      },
      "practice_problems": [
        {
          "file_id": "...",
          "filename": "...",
          "page": 143,
          "snippet": "Problem 5.2.2: Assign link polarities..."
        }
      ],
      "key_terms": ["Ceteris Paribus", "Polarity", "Feedback Loop"],
      "confidence_score": 0.85  # Average retrieval score
    }
  ]
}

Implementation:
Create app/tools/rag_scout.py with function:

def enrich_coverage(
    coverage: ExamCoverage,
    retrieval_top_k: int = 10,
    min_score: float = 0.7,
    use_chapter_filter: bool = True
) -> EnrichedCoverage:
    """
    For each topic bullet:
    1. Query FAISS with bullet text
    2. If use_chapter_filter=True and topic has chapter number:
       - First try: filter to chunks with matching chapter_number
       - If < 3 results: fall back to full-textbook search
    3. Filter chunks by score >= min_score
    4. For chunks with section_type="explanation": collect pages, consolidate into ranges
    5. For chunks with section_type="problems": extract problem references with regex
    6. Extract capitalized phrases (2-4 words) as potential key terms
    7. Calculate confidence score (average retrieval score)
    8. Store results in enriched structure
    """

Logic details:

A) Chapter-aware filtering (NEW - leverages Phase 4.5 TOC):
- Each topic bullet has a chapter number (from coverage JSON)
- Query FAISS with bullet text + filter: chapter_number == topic.chapter
- This dramatically improves precision by eliminating chunks from other chapters
- Fallback strategy if chapter filter returns < 3 results:
  * Remove chapter filter and search full textbook
  * Helps when chapter numbers don't align perfectly or TOC is missing
- Benefits:
  * Coverage says "Chapter 5: Polarity rules" → only retrieve Chapter 5 chunks
  * Avoids false matches from Chapter 8 or Chapter 12 that mention same concepts

B) Page range consolidation:
- Collect all page_start and page_end from retrieved chunks
- Sort pages: [137, 138, 139, 155, 156, 202, 203]
- Merge consecutive pages (within 3 pages): [[137, 139], [155, 156], [202, 203]]

C) Practice problem extraction:
- Filter chunks with section_type="problems"
- Use regex to find patterns:
  * "Problem \d+\.?\d*"
  * "Exercise \d+"
  * "Challenge \d+\.\d+\.\d+"
- Extract page number + snippet (first 100 chars)

D) Key term extraction:
- From top 3 retrieved chunks, extract:
  * Capitalized phrases (2-4 words)
  * Filter common words (The, A, This, In, etc.)
  * Return top 5-8 terms by frequency across chunks

E) Confidence scoring:
- Average of retrieval scores from top K chunks
- If avg_score < 0.6: flag as low confidence (warn user during plan generation)

Constraints:
- Do NOT use LLM for this phase - purely retrieval + heuristics
- If no chunks retrieved above min_score, mark reading_pages and practice_problems as empty
- Update manifest to track enriched_coverage artifacts
- Chapter filtering is enabled by default but gracefully degrades if TOC metadata unavailable

Implementation notes:
- The chapter_number filter in FAISS search requires post-filtering retrieved chunks
- FAISS returns top_k results, then filter by chapter_number in Python
- If filtered results < 3, re-query without chapter filter
- Log when fallback to full-textbook search occurs (helps debug TOC issues)

CLI test:
`python -m app.cli.enrich_coverage --exam-file {coverage_file_id}`
prints:
- Chapter 1, Bullet 1: Found 3 page ranges, 2 problems, 6 terms (confidence: 0.85)
- Chapter 1, Bullet 2: Found 1 page range, 0 problems, 4 terms (confidence: 0.72)
- ...
- Summary: 45/50 topics enriched with high confidence

Add:
- app/models/enriched_coverage.py (Pydantic models)
- app/tools/rag_scout.py
- app/cli/enrich_coverage.py
```

---

# Phase 8 — Multi-Exam Planner: Generate interleaved study schedules

## Deliverable

* Generate comprehensive, multi-exam study plan with interleaved scheduling
* Output matches the target schema: Date | Exam | Topic | Objective | Pages | Problems | Terms | Golden Question | Time
* Support multiple scheduling strategies (round-robin, priority-first, balanced)

## Cursor prompt (Phase 8)

```text
Implement Phase 8: Multi-exam interleaved study plan generator.

Context:
- We have multiple EnrichedCoverage JSONs (one per exam)
- User can select multiple exams to study for simultaneously
- Goal: Generate ONE unified study plan that interleaves topics from multiple exams

Input:
- exam_ids: list[str]  # file_ids of exam coverage files
- start_date: date
- end_date: date (or derive from earliest exam_date - 3 days buffer)
- study_minutes_per_day: int = 90
- interleave_strategy: "round_robin" | "priority_first" | "balanced"

Output:
StudyPlan JSON at storage/state/plans/{plan_id}.json

Schema:
{
  "plan_id": "uuid",
  "created_at": "ISO",
  "exams": [
    {"exam_id": "...", "exam_name": "...", "exam_date": "...", "course": "SYSD 300", "priority": 1}
  ],
  "total_days": 20,
  "total_study_hours": 30,
  "strategy": "balanced",
  "days": [
    {
      "date": "2026-02-10",
      "day_name": "Tuesday",
      "total_minutes": 135,
      "blocks": [
        {
          "exam_id": "...",
          "exam_name": "Midterm 1: SD Fundamentals",
          "course": "SYSD 300",
          "chapter": "5",
          "topic": "Ch 5: Causal Loop Diagrams",
          "objective": "Master the rules for assigning link and loop polarity (+/- and R/B).",
          "reading_pages": "Sterman, pp. 137-155",
          "practice_problems": "Challenge 5.2.2: Assigning Link Polarities (p. 143)",
          "key_terms": ["Ceteris Paribus", "Polarity", "Feedback Loop", "Delay"],
          "visuals": [],  # Optional: figure references if extractable
          "golden_question": "Why must you use the 'Ceteris Paribus' assumption when signing a link?",
          "prerequisite_check": "Review Feedback Basics (Ch 1.1.3) if you forget loop logic.",
          "time_estimate_minutes": 75,
          "confidence_score": 0.85
        }
      ]
    }
  ]
}

Implementation:
Create app/tools/study_planner.py:

def generate_multi_exam_plan(
    exam_file_ids: list[str],
    start_date: date,
    end_date: date,
    minutes_per_day: int = 90,
    strategy: str = "balanced"
) -> StudyPlan:
    """
    Steps:
    1. Load all EnrichedCoverage JSONs for exam_file_ids
    2. Sort exams by exam_date (earliest first gets higher priority)
    3. Flatten all topics into a work queue with metadata:
       - Estimate minutes per topic:
         * Base: 30 minutes
         * +20 if practice_problems exist and count > 2
         * +15 if chapter <= 3 (foundational material needs more time)
         * +10 if confidence_score < 0.7 (low confidence = needs more exploration)
       - Assign priority weight based on exam urgency
    
    4. Allocate topics to days using interleaving strategy:
       
       Round-robin:
       - Cycle through exams evenly: ABCABC...
       
       Priority-first:
       - Fill each day with highest-priority exam until 50% complete, then next exam
       
       Balanced:
       - Aim for equal total minutes per exam across entire plan
       - Track cumulative minutes per exam, schedule from exam with least minutes
    
    5. For each scheduled topic, generate:
       - golden_question: Call LLM to generate Socratic question
       - prerequisite_check: Call LLM to infer prerequisite knowledge (optional)
    
    6. Format reading_pages and practice_problems as readable strings
    7. Output final JSON
    """

Golden Question Generation (use google-genai with gemini-2.0-flash):
Prompt template:
"Given this learning objective: '{objective}' and key terms: {terms}, generate ONE concise Socratic question that tests deep understanding, not just recall. The question should require reasoning and synthesis. Start with 'Why...' or 'How...' and keep it under 20 words."

Prerequisite Check Generation (optional):
Prompt template:
"For the topic '{topic}' in chapter {chapter}, what prior knowledge or earlier chapter concepts should a student review first? Answer in one sentence: 'Review [concept] from [location] if you [condition].'"

Constraints:
- Do NOT guess content. If EnrichedCoverage is missing data (no pages/problems), create block with empty fields but include a note.
- Time estimates are heuristic-based.
- If a topic has confidence_score < 0.6, add a warning note in the block.
- Allow multiple blocks per day up to minutes_per_day limit.
- If remaining topics don't fit, add extra days.

Reading pages formatting:
From: {"file_id": "...", "filename": "Sterman.pdf", "page_ranges": [[137, 155]]}
To: "Sterman, pp. 137-155"

Practice problems formatting:
From: [{"page": 143, "snippet": "Problem 5.2.2: ..."}]
To: "Problem 5.2.2 (p. 143)"

CLI test:
`python -m app.cli.generate_plan --exams {file_id1},{file_id2} --start 2026-02-08 --end 2026-02-27 --minutes 120 --strategy balanced`

prints:
- Plan created: {plan_id}
- Exams: SYSD 300 Midterm 1, PHYS 234 Midterm 1
- Total days: 19, Total hours: 38
- Day 1 (Feb 8): 120 min, 2 topics (SYSD Ch1, PHYS Ch1)
- ...

Add:
- app/models/plan.py (StudyPlan, StudyBlock Pydantic models)
- app/tools/study_planner.py
- app/tools/question_generator.py (for Socratic questions)
- app/cli/generate_plan.py
```

---

# Phase 9 — Plan Export: CSV and Markdown output

## Deliverable

* Export study plan to readable formats: CSV and Markdown
* Match the target format provided by user
* Support filtering by exam or date range

## Cursor prompt (Phase 9)

```text
Implement Phase 9: Export study plan to readable formats.

Context:
We have StudyPlan JSON with all fields populated (from Phase 8).
User wants to view and print plans in CSV or Markdown format.

Goal:
Create export functions for CSV and Markdown with clean formatting.

Implementation:
Create app/tools/plan_export.py:

1. export_to_csv(plan: StudyPlan, output_path: Path, exam_filter: list[str] = None)
   Columns (in order):
   - Date
   - Day (e.g., "Tuesday")
   - Exam / Course (e.g., "SYSD 300: Midterm 1")
   - Chapter / Topic
   - Learning Objective
   - Required Readings (pages)
   - Practice Problems
   - Key Terms to Know
   - Golden Question
   - Prerequisite Check
   - Time Estimate (minutes)
   
   Format:
   - One row per block
   - Key terms as comma-separated string
   - Empty cells if data not available
   - Use proper CSV escaping for quotes and commas

2. export_to_markdown(plan: StudyPlan, output_path: Path, exam_filter: list[str] = None)
   Format:
   - Title: "Study Plan: {exam names}"
   - Metadata table: Total days, Total hours, Strategy, Date range
   - Per-day sections:
     * Day header: "## Tuesday, February 10 (120 minutes)"
     * Table with columns: Exam | Topic | Objective | Resources | Time
     * Resources column: "📖 Pages: ...\n📝 Problems: ...\n💡 Terms: ...\n❓ Question: ..."
   - Include emoji indicators:
     * 📊 for statistics/data courses
     * ⚛️ for physics courses
     * 🔁 for systems dynamics
     * 🧮 for calculus/math
   - Footer: "Generated by Study Agent on {date}"

3. export_to_json(plan: StudyPlan, output_path: Path)
   - Pretty-printed JSON with indent=2
   - Already have the model, just save it

CLI commands:
`python -m app.cli.export_plan --plan {plan_id} --format csv --output study_plan.csv`
`python -m app.cli.export_plan --plan {plan_id} --format md --output study_plan.md`
`python -m app.cli.export_plan --plan {plan_id} --format json --output study_plan.json`

Optional filters:
`--exam {exam_id}` to export only blocks for specific exam
`--start {date}` and `--end {date}` to export date range

Add:
- app/tools/plan_export.py
- app/cli/export_plan.py
```

---

# Phase 10 — ADK Integration: Root agent + tool orchestration

## Deliverable

* ADK root agent running in chat UI
* Automatic sync on each turn (ingest new files)
* Readiness checks before generating plans
* Structured error responses for missing materials

## Cursor prompt (Phase 10)

```text
Implement Phase 10: Integrate all tools into Google ADK agents.

Context:
We have working tools:
- update_manifest, extract_text, classify_docs, extract_coverage
- chunk_textbook, build_index, enrich_coverage
- generate_multi_exam_plan, export_plan

Goal:
Create ADK agents that orchestrate the full pipeline and interact with users.

RootAgent behavior:
1. On every user turn:
   - Run sync: update_manifest() → process any new/stale files through pipeline
   - Detect user intent from message

2. User intent routing:

   a) "Create study plan" / "Plan my exams" / "Generate schedule"
      - Extract: exam_ids (or ask user to clarify), start_date, end_date, minutes_per_day
      - Check readiness:
        * Do we have coverage for requested exams?
        * Do we have enriched_coverage for requested exams?
        * Do we have textbook chunks indexed?
      - If missing:
        * Coverage: "Please upload exam overview for {course}"
        * Enriched coverage: Run enrich_coverage() for each exam (might take time, show progress)
        * Textbook chunks: "Please upload textbook: {expected_textbook_name}"
      - If ready: Call generate_multi_exam_plan()
      - Return plan summary + offer to export to CSV/Markdown

   b) "What's covered on {exam}?" / "Show exam topics"
      - Check: Do we have coverage JSON?
      - If not: Ask user to upload exam overview
      - If ready: Return structured coverage summary with confidence scores from enriched coverage

   c) "Explain {concept}" / Question about topic
      - Use FAISS retrieval to find relevant chunks
      - Generate answer with LLM grounded in retrieved chunks
      - Return answer with page citations
      - If exam context specified, filter chunks to that exam's chapters

   d) "Export my plan as {format}"
      - Check: Does user have a plan?
      - If yes: Call export_plan() with specified format
      - Return file path or content

3. Missing materials response format:
   {
     "status": "incomplete",
     "missing": [
       {
         "type": "textbook",
         "for_exam": "midterm_1",
         "expected": "Sterman - Business Dynamics",
         "message": "Upload the Sterman textbook to enable page-specific recommendations"
       },
       {
         "type": "exam_overview",
         "for_course": "PHYS 234",
         "message": "Upload the PHYS 234 Midterm 1 Overview to define exam scope"
       }
     ],
     "available_exams": ["SYSD 300 Midterm 1", "HLTH 204 Midterm 1"],
     "message": "I need the following materials to create your complete plan..."
   }

Tools available to RootAgent (create ADK tool wrappers):
- sync_files() -> runs manifest update + processes new/stale files
- check_readiness(intent: str, exam_ids: list[str]) -> dict
- list_available_exams() -> list[dict]
- enrich_coverage_for_exam(exam_file_id: str) -> dict
- generate_plan(exam_file_ids: list[str], start_date, end_date, minutes, strategy) -> dict
- search_textbook(query: str, exam_scope: str = None, top_k: int = 5) -> list[dict]
- export_plan(plan_id: str, format: str, output_path: str) -> str

Constraints:
- NEVER guess exam content or make up page numbers
- NEVER create plan without enriched coverage
- If RAG Scout returns low-confidence results (<0.6 avg), warn user:
  "Some topics have low confidence matches. The textbook might not align perfectly with exam coverage. Review the plan carefully."
- Always show progress for long-running operations (enrichment, indexing)

Implementation files:
- app/agents/root_agent.py (ADK agent definition)
- app/agents/tools.py (ADK tool wrappers for all functions)
- app/tools/readiness.py (enhanced with enrichment checks)
- app/main.py (ADK app entrypoint with chat UI)

Tool calling pattern:
- Tools should return structured dicts (JSON-serializable)
- Root agent interprets results and formats user-friendly responses
- Use rich library for progress bars and formatted output in CLI

Logging:
- Log all tool calls to storage/state/logs/trace.jsonl
- Format: {"timestamp": "...", "tool": "...", "input": {...}, "output": {...}, "duration_ms": ...}

Run with:
`python -m app.main`
Opens ADK chat UI in terminal or web interface.

Add:
- app/agents/root_agent.py
- app/agents/tools.py
- app/tools/readiness.py (update existing)
- app/main.py
```

---

# Phase 11 — Tutor Q&A Pipeline (RAG answering with evidence)

## Deliverable

* Given a question + optional exam context, retrieve chunks and generate grounded answer
* Answers must cite sources (chunk_id + file + page range)
* Separate from study plan generation - this is for tutoring questions

## Cursor prompt (Phase 11)

```text
Implement Phase 11: Tutor Q&A pipeline for exam-scoped questions.

Context:
We have FAISS retrieval returning chunks with page metadata.
We have exam coverage that defines scope.
This is separate from plan generation - used for answering specific questions.

Goal:
Implement app/tools/tutor_answer.py:

Input:
- question: str
- exam_id: str (optional, to filter by exam scope)
- top_k: int = 8

Output:
{
  "answer": "...",
  "citations": [
    {
      "chunk_id": "...",
      "file_id": "...",
      "filename": "Sterman - Business Dynamics.pdf",
      "page_start": 137,
      "page_end": 139,
      "relevance_score": 0.85
    }
  ],
  "scope": {
    "exam_id": "midterm_1",
    "exam_name": "...",
    "chapters": [1, 2, 3]
  },
  "confidence": "high" | "medium" | "low"
}

Process:
1. If exam_id provided:
   - Load coverage to get chapter list
   - Filter retrieval to chunks from those chapters (if possible)

2. Retrieve top_k chunks using FAISS

3. If average retrieval score < 0.6:
   - Return {"answer": "I couldn't find strong matches in the textbook for this question.", "confidence": "low"}

4. Call LLM (gemini-2.0-flash) with prompt:
   "You are a tutor helping a student prepare for an exam. Answer the following question using ONLY the information provided in the context below. If the context doesn't contain enough information, say so. Cite specific page numbers when possible.
   
   Question: {question}
   
   Context:
   {chunk_texts_with_pages}
   
   Answer:"

5. Extract citations from retrieved chunks

6. Determine confidence:
   - high: avg_score >= 0.75
   - medium: 0.6 <= avg_score < 0.75
   - low: avg_score < 0.6

Constraints:
- If no chunks retrieved above threshold, do NOT guess
- Prompt must instruct model to stay grounded in provided chunks
- Include page numbers in citations for easy reference
- No ADK wiring yet; just tool function

CLI test:
`python -m app.cli.ask --exam midterm_1 "What is policy resistance?"`
prints:
- Answer: ...
- Citations: Sterman, pp. 15-17 (score: 0.87), pp. 22-23 (score: 0.81)
- Confidence: high

Add:
- app/tools/tutor_answer.py
- app/cli/ask.py
```

---

# Phase 12 — Polish and Improvements (optional, as needed)

* Better exam_id naming (user-friendly vs auto-generated)
* Hybrid retrieval (BM25 + vector semantic search)
* Textbook table of contents extraction for chapter-aware filtering
* Verifier agent to double-check answer grounding
* UI improvements (web interface instead of CLI)
* Comprehensive test suite
* Figure/visual reference extraction from PDFs
* Math equation parsing improvements (OCR for equations)

(Implement these as needed based on testing and user feedback)

---

## Important Implementation Notes

### Why This Architecture Works

Each prompt:
* Bans future-phase features to prevent scope creep
* Defines exact deliverables and file paths
* Defines schemas explicitly with Pydantic models
* Defines CLI tests for validation
* Includes deterministic rules and constraints
* Separates concerns (retrieval vs generation vs orchestration)

### Critical Success Factors

1. **RAG Scout (Phase 7) is the linchpin**
   - This phase bridges abstract objectives to concrete resources
   - Quality of retrieval determines quality of final plan
   - Confidence scores enable transparency about match quality

2. **Enriched Coverage is human-reviewable**
   - User should review enriched_coverage before generating plan
   - Allow manual corrections to page ranges and problems
   - System assists, human validates

3. **Multi-exam interleaving is the differentiator**
   - Most study tools handle one exam at a time
   - Interleaving improves retention and time management
   - Different strategies suit different student needs

4. **Determinism where possible, LLM where needed**
   - File operations: deterministic
   - Document classification: heuristics (Phase 3)
   - Coverage extraction: LLM (Phase 4)
   - Chunking: deterministic
   - Retrieval: semantic similarity
   - Enrichment: retrieval + heuristics
   - Planning: LLM for questions, deterministic for scheduling

### Common Pitfalls to Avoid

* Don't let Cursor add features from future phases
* Don't skip the enrichment step (Phase 7) - it's critical
* Don't over-rely on LLMs for structured extraction (use Pydantic)
* Don't ignore confidence scores - surface them to users
* Don't assume textbooks match exam coverage perfectly

---

## Recommended Execution Order

**Completed:** Phases 1-4 ✅

**Next:** 
1. Phase 5 (verify/enhance chunking with section_type)
2. Phase 6 (embeddings with modern SDK + FAISS)
3. Phase 7 (RAG Scout - THE KEY PHASE)
4. Phase 8 (Multi-exam planner)
5. Phase 9 (Export to CSV/MD)
6. Phase 10 (ADK integration)
7. Phase 11 (Tutor Q&A - can be parallel with Phase 10)
8. Phase 12 (Polish as needed)

**Testing strategy:**
- After Phase 7: Manually review enriched coverage for 2-3 topics to validate retrieval quality
- After Phase 8: Generate a 3-day plan for 2 exams and verify formatting
- After Phase 10: Full end-to-end test with real uploads

Good luck! 🚀
