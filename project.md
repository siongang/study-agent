study_agent/
  app/
    __init__.py
    main.py                     # ADK entrypoint (root agent)
    agents/
      root_agent.py
      ingest_agent.py
      tutor_agent.py
      planner_agent.py
      verifier_agent.py
    tools/
      fs_scan.py
      pdf_extract.py
      doc_classify.py
      chunking.py
      embed.py
      vector_store.py
      retrieve.py
      readiness.py
      coverage_extract.py
      study_plan.py
    models/
      manifest.py
      coverage.py
      chunks.py
      plan.py
    storage/
      uploads/                   # raw user uploads (unstructured)
      state/
        manifest.json
        coverage/
        chunks/
        index/
  tests/
  requirements.txt
  .env



I. The Deterministic Data Plane (Phases 1–6)
This is the foundation you're building first. It's code-driven and 100% predictable.

User Uploads: You drop PDFs (Syllabus, Overview, Textbook) into storage/uploads/.

manifest.json (Phase 1): A script scans the folder, generates a SHA-256 hash for each file, and creates a record. This prevents re-processing files that haven't changed.

Text Extraction (Phase 2): PyMuPDF reads the PDFs and saves clean text into storage/state/extracted_text/. It uses "blocks" mode to keep multi-column textbook layouts in the right reading order.

Classification (Phase 3): Simple keyword rules (not an LLM!) look for words like "Syllabus" or "Midterm" to label your files as syllabus, exam_overview, or textbook.

Coverage Extraction (Phase 4): Regex logic pulls the "Source of Truth" from the Midterm Overview (e.g., "Feb 27" and "Chapters 1–5").

Chunk & Index (Phases 5–6): The textbook is broken into 600–900 token segments (Chunks) and turned into mathematical vectors (Embeddings) stored in a local FAISS/Chroma index.

II. The Agentic Logic Plane (Phases 7–10)
This is where the "Agent" wakes up and uses the data you've prepared.

Readiness Gate (Phase 7): A specialized tool checks the manifest. If you have the "Midterm Overview" but only have the "Textbook" for Chapters 1–3, the agent stops and asks you for the missing chapters.

Study Plan Brain (Phase 9):

The "What": The agent pulls the topic bullets from the Midterm Overview.

The "When": It checks the Syllabus for assignment dates and weights.

The "How": It uses RAG to find the exact pages in your textbook for each topic.

The Output: It synthesizes a daily schedule (JSON) that links every study task to a specific resource.

Root Agent Orchestration (Phase 10): The manager that listens to you, runs the "Sync" check on your files, and decides whether to send your question to the Tutor or the Planner.

Why RAG is the "Glue"
In this system, RAG is used to bridge the gap between your files and the study plan.

Retrieval: The agent searches the index for "Poisson Distribution" (from your Midterm Overview).

Augmentation: It adds that textbook text to its own prompt.

Generation: It writes a study task: "Review the Poisson Approximation to the Binomial (Textbook p. 214) for 20 minutes."

Without RAG, the agent would just give you generic "study advice." With RAG, it gives you a personalized map of your own course materials.

Would you like me to generate the Phase 1 "Manifest" code for you to copy into app/tools/fs_scan.py to get started?

Practical RAG Pipeline for Document Analysis