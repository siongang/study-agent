Below is a **thorough execution plan** broken into phases, and for **each phase** I’m giving you a **Cursor-ready prompt** that includes the exact context/constraints so Cursor doesn’t invent architecture or skip steps.

This plan assumes:

* **Google ADK** for agents + tool calling
* **local file-based storage** for uploads + state
* **local RAG** with FAISS *or* Chroma (choose one; prompts default to **FAISS** but I include an alternate prompt for Chroma)
* PDFs are the primary inputs (syllabus, exam overviews, textbook chapters)
* We must support **multiple exams** and avoid guessing exam coverage

---

tbook for RAG
  5. answers questions with evidence
  6. generates a study plan (JSON + readable)

**Absolute rules**

* Root agent must **never guess** exam scope.
* If required materials are missing, the system must return a **structured “missing items” response** that the root agent uses to ask the user to upload them.
* Use deterministic checks for readiness/coverage (tool logic), not LLM vibes.
* Only use LLM for: explanation synthesis, planning text, optional fallback classification (optional later).

**Storage layout**

```
storage/
  uploads/                # raw user uploads (user-controlled, unstructured)
  state/
    manifest.json
    extracted_text/        # per file extracted text cache
    chunks/                # chunk store
    index/                 # vector index + mappings
    coverage/              # per-exam coverage JSON
    logs/                  # tool call traces
```

**Packages available**

* google-adk, google-generativeai, pymupdf, pdfplumber, tiktoken, faiss-cpu, pydantic, tqdm, numpy, python-dotenv, rich

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
- Do NOT hardcode HLTH 204 specifically; make it generic.
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

* For each `exam_overview`, generate `storage/state/coverage/<exam_id>.json`
* Extract:

  * exam label/name (midterm_1 if possible, else derived)
  * exam date if present
  * covered chapters list
  * per-chapter topic bullets
* This coverage JSON is **source of truth** for exam scope

## Cursor prompt (Phase 4)

```text
Implement Phase 4: extract exam coverage from exam overview documents.

Context:
Manifest now includes doc_type. For doc_type=="exam_overview" we have extracted text cached.
We need structured exam scope to avoid guessing.

Goal:
For each exam_overview:
- Parse full_text to extract:
  - exam_name (e.g., "Midterm Examination 1" or similar)
  - exam_date if present (best-effort parse; store as raw string if needed)
  - covered chapters list (e.g. "Coverage: Chapters 1,2,3,4,5")
  - structured outline: Chapter headings + bullet topics under each chapter
- Output JSON at `storage/state/coverage/{exam_id}.json` with schema:
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
- Use regex + text parsing, robust to formatting
- If chapter list cannot be parsed, keep chapters empty but still output topics where possible
- Update manifest derived artifacts list for that file
- Do NOT use LLM

Add CLI:
`python -m app.cli.extract_coverage`
prints coverage summary (exam_id, chapters, #topics).
```

---

# Phase 5 — Chunking (token-based) + chunk store

## Deliverable

* Chunk all **textbook** docs (and optionally exam/syllabus) into chunks
* Store as JSONL or Parquet in `storage/state/chunks/chunks.jsonl`
* Each chunk has stable `chunk_id`, file_id, page range, token count, metadata

## Cursor prompt (Phase 5)

```text
Implement Phase 5: token-based chunking and chunk storage.

Context:
We have extracted text cached and doc_type classified.
Now we create chunks for retrieval later.

Goal:
Chunk documents where doc_type=="textbook" (optionally include syllabus/exam_overview but default only textbook).
Chunking rules:
- target 600-900 tokens per chunk
- overlap 100-150 tokens
- use tiktoken for token counting
- preserve metadata:
  - file_id, filename, doc_type
  - page_start/page_end
  - token_count
  - text

Chunk ID:
- deterministic: sha1(file_sha256 + ":" + page_start + "-" + page_end + ":" + chunk_index)

Store:
- `storage/state/chunks/chunks.jsonl` (one JSON per line)
- also store `storage/state/chunks/chunk_index.json` mapping chunk_id -> {file_id, page_start, page_end}

Implementation:
- app/models/chunks.py
- app/tools/chunking.py
- app/tools/chunk_store.py (append + rebuild safely)
- Only (re)chunk files that are new/stale or whose chunks missing.
- Update manifest derived artifacts list accordingly.

Add CLI:
`python -m app.cli.chunk_textbook`
prints #chunks created per file.
No embeddings yet.
```

---

# Phase 6 — Embeddings + FAISS index (local RAG foundation)

## Deliverable

* Embed chunk texts with `google-generativeai` embeddings
* Build FAISS index
* Maintain mapping FAISS row → chunk_id
* Support search returning top_k chunks

## Cursor prompt (Phase 6 — FAISS)

```text
Implement Phase 6: embeddings + FAISS index for chunks.

Context:
Chunks exist in `storage/state/chunks/chunks.jsonl`.
We want local semantic retrieval.

Goal:
- Embed each chunk text (cache per chunk_id)
- Build FAISS index and persist it
Files:
- `storage/state/index/faiss.index`
- `storage/state/index/row_to_chunk_id.json`
- `storage/state/index/embeddings_cache/{chunk_id}.npy` (or a single embeddings.npy + index)

Implementation:
- app/tools/embed.py:
  - embed_texts(texts:list[str]) -> np.ndarray
  - use google-generativeai embedding model
  - handle batching, retries, rate limits lightly
- app/tools/faiss_store.py:
  - build_or_update_index(chunks)
  - search(query_text, top_k) -> list[{chunk_id, score}]
- app/tools/retrieve.py:
  - retrieve_chunks(question, top_k, filters?) -> list[Chunk]

Constraints:
- Rebuild index if schema changes; otherwise allow incremental add (optional).
- For MVP, rebuild entire index when any chunk changes is acceptable.
- No LLM answering yet—just retrieval API.

Add CLI:
`python -m app.cli.search "binomial distribution"`
prints top chunk ids + snippet.
```

### Alternate Cursor prompt (Phase 6 — Chroma)

If you decide Chroma instead, ask and I’ll drop the exact Chroma prompt.

---

# Phase 7 — Readiness + coverage gating (no guessing)

## Deliverable

* Tool that decides if system can:

  * generate study plan for exam X
  * answer question scoped to exam X
* Returns missing items list

## Cursor prompt (Phase 7)

```text
Implement Phase 7: readiness and coverage gating.

Context:
We have:
- manifest with doc_types
- exam coverage JSON in storage/state/coverage/
- FAISS retrieval available for chunks

Goal:
Create deterministic tool functions:
1) assess_readiness(intent:str, exam_id:Optional[str]) -> dict
Intents:
- "study_plan"
- "exam_question"
- "course_logistics"

Rules:
- study_plan requires:
  - at least one exam coverage JSON for exam_id
  - at least some textbook chunks indexed (FAISS exists)
- exam_question requires:
  - exam_id coverage exists OR if exam_id missing, list available exams and request user pick
- course_logistics requires syllabus exists

Return shape:
{
  "ready": bool,
  "missing": [ ... ],
  "available_exams": [ ... ],
  "notes": [ ... ]
}

Also implement:
2) list_available_exams() by reading coverage folder

Add:
- app/tools/readiness.py
- unit tests for readiness behavior
No ADK integration yet.
```

---

# Phase 8 — Tutor Q&A pipeline (RAG answering with evidence)

## Deliverable

* Given a question + exam_id, retrieve chunks and produce grounded answer
* Answers must cite chunk sources (chunk_id + file + page range)

## Cursor prompt (Phase 8)

```text
Implement Phase 8: Tutor Q&A pipeline using retrieval + grounded generation.

Context:
We have FAISS retrieval returning chunks.
We have exam coverage that defines scope.

Goal:
Implement app/tools/tutor_answer.py:
- input: question, exam_id (optional)
- step 1: readiness check (Phase 7)
- step 2: retrieve top_k chunks (e.g. 6-10)
- step 3: call LLM to generate answer strictly grounded in retrieved chunks
- step 4: output:
  {
    "answer": "...",
    "citations": [
      {"chunk_id":"...", "file_id":"...", "filename":"...", "page_start":1, "page_end":2}
    ],
    "scope": {"exam_id":"...", "chapters":[...]}
  }

Constraints:
- If no chunks retrieved above a threshold, return missing material response (do not guess).
- Prompt must instruct model to avoid adding facts not present in chunks.
- No ADK wiring yet; just tool function + CLI:
  `python -m app.cli.ask --exam midterm_1 "Is Poisson on the exam?"`
```

---

# Phase 9 — Study plan generation (coverage → plan JSON)

## Deliverable

* Generate structured study plan JSON for selected exam_id
* Attach resources (chunk refs) per concept
* Produce readable output

## Cursor prompt (Phase 9)

```text
Implement Phase 9: Study plan generation.

Context:
We have:
- coverage JSON listing chapters and topic bullets per chapter
- retrieval over textbook chunks

Goal:
Implement app/tools/study_plan.py:
- input: exam_id, minutes_per_day default 90, start_date optional, end_date optional
- load coverage JSON
- derive a concept list from topics bullets (each bullet becomes a "concept task" initially)
- estimate minutes per concept:
  - base 15 minutes
  - +5 per keyword like "calculate", "probability", "distribution"
- retrieve 2-3 supporting chunks per concept using bullet text as query
- schedule concepts in chapter order across days until exam date (if known; else schedule 7-day plan)
- output StudyPlan JSON:
  {
    "exam_id": "...",
    "assumptions": {...},
    "days": [
      {"date":"YYYY-MM-DD","blocks":[{"concept":"...","minutes":30,"resources":[...]}]}
    ]
  }

Also add CLI:
`python -m app.cli.plan --exam midterm_1 --minutes 90`
prints plan.
No ADK wiring yet.
```

---

# Phase 10 — ADK integration (root agent + tool calling + chat UI)

## Deliverable

* ADK root agent running in chat UI
* On each user message:

  * detect file changes and ingest as needed
  * route to tutor or planner
  * if missing materials, ask user to upload

## Cursor prompt (Phase 10)

```text
Implement Phase 10: integrate tools into Google ADK agents and run in ADK chat UI.

Context:
We have working tools:
- update_manifest, extract_text, classify_docs, extract_coverage, chunking, build_faiss, readiness, tutor_answer, generate_study_plan

Goal:
Create ADK agents:
1) RootAgent:
- first action on each user turn: run a lightweight "sync" (update manifest and run missing pipeline steps for new/stale files)
- determine user intent:
  - "study plan" -> call generate_study_plan
  - question -> call tutor_answer
  - logistics -> answer using retrieval from syllabus chunks (optional)
- if readiness says missing material -> ask user to upload specific docs

2) IngestAgent (can be internal helper called by root):
- runs sequential pipeline steps for new/stale files:
  update_manifest -> extract_text -> classify -> if exam_overview extract_coverage -> if textbook chunk -> embeddings/index rebuild

ADK constraints:
- Root agent must not guess. It must rely on readiness tool results.
- Tools should return structured dicts (JSON-serializable).
- Provide a minimal `app/main.py` entrypoint to run ADK chat UI.

Also add:
- simple logging of tool calls to storage/state/logs/trace.jsonl

Do NOT add new features beyond wiring. Keep it stable.
```

---

# Phase 11 — Polishing (optional, only if time)

* Better exam_id naming (midterm_1 vs inferred)
* Hybrid retrieval (BM25 + vector)
* Verifier agent to ensure answer grounded
* UI improvements, rich output
* Tests around each tool

(I won’t dump prompts for this unless you want.)

---

## Important note (why this solves your “Cursor hallucination” issue)

Each prompt:

* bans future-phase features
* defines exact deliverables and file paths
* defines schema
* defines CLI tests
* defines allowed doc types and behaviors
* includes deterministic rules and constraints

Cursor tends to hallucinate when:

* requirements are implicit
* schema is unclear
* phases aren’t isolated

These prompts remove those failure modes.

---

If you want, I can also generate a **single “master Cursor prompt”** that tells Cursor to scaffold the repo + generate *Phase 1–4 only* in one shot (some people prefer that), but I recommend running phase-by-phase to keep control.
