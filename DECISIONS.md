# Architectural Decisions — Docstract

This document explains the key technical decisions made while building Docstract and the reasoning behind each one.

---

## 1. Why Pydantic for schema validation?

**Decision:** Use Pydantic v2 to define document schemas and validate LLM outputs.

**Reasoning:**
LLMs return raw text — the same prompt can return slightly different structures on each run. Without validation, bad data silently enters the system. Pydantic acts as a strict gatekeeper:
- If the LLM returns a string where a float is expected, Pydantic throws a clear ValidationError
- Missing required fields are caught immediately
- Optional fields default to `None` gracefully instead of crashing

**Alternative considered:** Manual JSON parsing with try/except. Rejected because it requires writing custom validation logic for every field and doesn't scale when schemas change.

---

## 2. Why confidence scoring at the field level?

**Decision:** Score each extracted field individually (0–100%) rather than just pass/fail on the whole document.

**Reasoning:**
A document where 9/10 fields extracted correctly but 1 field is missing should not be treated the same as a completely failed extraction. Field-level scoring enables:
- Granular human review — only the uncertain fields need checking, not the whole document
- Actionable output — the system tells you exactly which fields to verify
- Better downstream decisions — downstream systems can use high-confidence fields immediately while flagging others

**Threshold chosen:** 70% — industry standard for document processing pipelines. Fields below 70% are flagged for human review.

---

## 3. Why ChromaDB for semantic search?

**Decision:** Use ChromaDB as a local vector database with sentence-transformers embeddings.

**Reasoning:**
The naive approach — sending the entire document to the LLM — fails for large documents (50+ pages) because:
- It exceeds context window limits
- Token cost scales linearly with document size
- LLM extraction quality degrades with too much irrelevant text

ChromaDB solves this by storing document chunks as vectors and retrieving only the 3–5 most relevant chunks per query. A 200-page document that would cost ~150,000 tokens gets reduced to ~2,000 tokens — a 99% reduction.

**Why local ChromaDB over cloud?** For a portfolio project, local ChromaDB deploys alongside the app without any additional service dependencies. In production, this would be swapped for ChromaDB Cloud or Pinecone.

---

## 4. Why sentence-transformers (all-MiniLM-L6-v2)?

**Decision:** Use the all-MiniLM-L6-v2 model for generating embeddings.

**Reasoning:**
- Free and runs locally — no API calls, no cost
- 384-dimensional vectors — small enough to be fast, large enough to be accurate
- Excellent performance on short-to-medium text passages (exactly what document chunks are)
- No internet dependency after initial download — works offline

**Alternative considered:** OpenAI's text-embedding-ada-002. Rejected because it adds API cost and dependency for a task that a free local model handles well.

---

## 5. Why separate modules instead of one big script?

**Decision:** Split the pipeline into `extractor.py`, `validator.py`, `confidence.py`, `batch_processor.py`, `report_generator.py`.

**Reasoning:**
Each module has a single responsibility. This means:
- You can re-run any stage independently without re-running the whole pipeline
- If validation logic changes, only `validator.py` needs updating
- Debugging is easier — you know exactly which stage failed
- Token cost is controlled — re-running the evaluator doesn't waste tokens re-calling the LLM

This follows the **Single Responsibility Principle** — a core software engineering practice.

---

## 6. Why a provider-agnostic cost registry?

**Decision:** Build a central `config.py` with pricing for 9 LLM providers that recalculates costs automatically when the model changes.

**Reasoning:**
Hardcoding OpenAI pricing into the code means the cost analysis is wrong the moment you switch models. By building a registry:
- Changing the model requires editing exactly one line in `config.py`
- All cost calculations across the entire system update automatically
- The frontend Token Intelligence panel can show comparative costs across all providers in real-time
- This mirrors how production AI systems manage model switching

---

## 7. Why FastAPI over Flask?

**Decision:** Use FastAPI for the REST API backend.

**Reasoning:**
- Automatic API documentation at `/docs` — useful for testing and sharing with interviewers
- Native Pydantic integration — request/response models validate automatically
- Async support — handles concurrent requests without blocking
- Type hints throughout — cleaner, more maintainable code
- Industry standard for Python AI/ML APIs in 2025–2026

---

## 8. Why vanilla HTML/CSS/JS for the frontend?

**Decision:** Build the frontend as a single self-contained HTML file with no frameworks.

**Reasoning:**
- Zero build step — open the file in a browser and it works
- No npm, no webpack, no dependencies to break
- Deploys as a static file served directly by FastAPI
- For a portfolio project demonstrating AI engineering, a clean functional frontend is sufficient — React would be overkill and add unnecessary complexity

---

## 9. Why archive instead of delete old extraction results?

**Decision:** When running a new batch, move old JSON files to a timestamped archive folder instead of deleting them.

**Reasoning:**
Deletion is irreversible. Archival lets you compare results across runs — useful for:
- Debugging when a new run performs worse than a previous one
- Demonstrating improvement over time
- Auditing extraction history in a production context

---

## 10. Why 500 words as the semantic search threshold?

**Decision:** Documents under 500 words are sent directly to the LLM; documents over 500 words use semantic search first.

**Reasoning:**
- Your sample documents (invoices, resumes, emails) are 100–200 words — well under the threshold
- For these short documents, semantic search adds latency without benefit
- The 500-word threshold is roughly equivalent to 1 A4 page — a natural boundary between "short document" and "needs chunking"
- The threshold is configurable in `extractor.py` (`SEMANTIC_SEARCH_THRESHOLD = 500`) for easy adjustment

---

## Known Limitations & Roadmap

| Limitation | Current State | Planned Fix |
|------------|---------------|-------------|
| Input format | Text only | PDF via pdfplumber, images via pytesseract |
| Resume format | Text only | DOCX via python-docx |
| Email format | Text only | Native .eml parsing |
| GSTIN verification | Format check only | GST Portal API integration |
| Confidence scoring | Local signals only | External API verification |
