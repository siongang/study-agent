# Agentic Study Assistant

> A local, agentic system for textbook-based study planning and assistance with guaranteed topic coverage

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What is this?

An **agentic study planning system** that:

- Ingests large textbooks (PDFs), syllabus, and midterm information, and extracts structured knowledge
- Guarantees **100% topic coverage** before exams
- Generates day-by-day study plans with workload balancing
- Acts as a **grounded AI tutor** using RAG
- Automatically **re-ingests and replans** when textbooks change
- An interactive, dynamic, and intelligent system

Built using **multi-agent architecture** with Google's Agent Development Kit (ADK) principles.

---
Demo:
https://drive.google.com/drive/folders/1DSywzuY2KKrLZ1bSwnX1VQOy76ZdJ37t?usp=sharing

## Quick Start

### 1. Setup

```bash
# Clone and navigate
cd study-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API key
```

### 2. Add required materials (textbooks, midterm information, syllabus)

### 3. Run the agent

```bash
adk web
```

### 4. Example conversation

```
> I added physics and biology textbooks.
> Physics exam is Feb 21, biology is Feb 25.
> Make me a study plan.

[Agent ingests textbooks, extracts topics, generates plan...]

✓ Ingested 2 textbooks (42 topics total)
✓ Generated study plan: 18 days, avg 2.3 topics/day
✓ Coverage: 100%

Plan saved to data/plans/study_plan.md
```

---

## Architecture Overview

### Multi-Agent Design

```
┌─────────────┐
│ RootAgent   │ ← Intent detection, material registry
└──────┬──────┘
       ├─→ IngestionAgent  (PDF → topics + chunks + embeddings)
       ├─→ PlannerAgent    (topics → study plan)
       └─→ TutorAgent      (RAG-based Q&A)
```



---

## Core Workflow

### Phase 1: Ingestion (automatic)

1. **Parse PDF** → raw text + page numbers
2. **Extract topics** → structured topic inventory (source of truth)
3. **Chunk text** → overlapping chunks with topic IDs
4. **Embed chunks** → vector store for RAG

### Phase 2: Planning

1. **Load topic inventories** from all textbooks
2. **Allocate topics to days** (today → exam date)
3. **Verify coverage** (all topics scheduled ≥1x)
4. **Check constraints** (workload limits, deadlines)

### Phase 3: Tutoring

- Query → retrieve relevant chunks → generate explanation
- Always cite page numbers and sections
- Offer practice questions

---

## Why This Architecture?

### From Google's Agent Guide

✅ **Grounding via RAG** — answers cite textbook pages  
✅ **Multi-agent orchestration** — specialized agents with clear roles  
✅ **Deterministic + LLM hybrid** — tools handle logic, agents handle reasoning  
✅ **Evaluation loops** — verifier agent ensures quality  
✅ **Stateful design** — material registry tracks changes

### From Software Engineering Best Practices

✅ **Separation of concerns** — agents, tools, schemas cleanly separated  
✅ **Reproducibility** — deterministic tools, versioned artifacts  
✅ **Extensibility** — easy to add new agents or tools  
✅ **Testability** — tools are pure functions  
✅ **Observability** — structured logs, clear state transitions

---
## Areas for Improvement
- Caching repeated llm requests. f.e generating questions
- Parallelizing Agents and long runnning tool calls
- Better and more consistent Rag System


## Example Use Cases

### 1. Initial setup

```
> I'm studying for three exams:
> - Physics (Feb 21)
> - Biology (Feb 25)
> - Chemistry (Mar 5)
> 
> I can study 3 hours per day.
> Make me a plan.
```

### 2. Textbook replacement

```
> I replaced my physics textbook with a newer edition.

[Agent detects change, re-ingests, invalidates plan]

> The old plan is now invalid. Want me to regenerate?
```

### 3. Tutoring

```
> Explain the difference between velocity and acceleration.

[Agent retrieves relevant chunks, generates explanation]

> Velocity is the rate of change of displacement (Physics, pp. 7-9).
> Acceleration is the rate of change of velocity (Physics, pp. 12-15).
> 
> Practice: Calculate acceleration given velocity at t=0 and t=5.
```

---

## Design Decisions

### Why local-only?

- No cloud dependencies = simpler, faster, more private
- Easier to demonstrate for take-home assessments
- Clear boundary: everything is an artifact on disk



### Why topic inventory before RAG?

- **Coverage guarantee** requires knowing what exists
- RAG is for retrieval, not structure inference
- Deterministic extraction = reproducible results

### Why multi-agent instead of single agent?

- **Clearer separation of concerns** (routing, ingestion, planning, tutoring)
- **Easier to test** and extend
- **Matches industry patterns** (per Google's ADK guide)

---

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Technical deep-dive
- [`docs/SETUP.md`](docs/SETUP.md) — Installation and configuration
- [`docs/USAGE.md`](docs/USAGE.md) — Detailed usage guide
- [`app/README.md`](app/README.md) — Code structure guide

---

## Requirements

- Python 3.12+
- ~2GB disk space (for vector indexes)
- Google API key (for Gemini models)

---

---

## Acknowledgments

Built following:
- Google's Agent Development Kit (ADK) patterns
- Google's agent architecture guide
- Software engineering best practices for production-grade agentic systems
