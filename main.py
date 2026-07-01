"""
main.py - FastAPI Backend
Project: Docstract - Intelligent Document Processor
Author: Ankur Sharma

What this does:
    - Exposes your entire extraction pipeline as a REST API
    - Anyone can send a document and get structured JSON back
    - No terminal needed — works via HTTP requests
    - Interactive docs auto-generated at http://localhost:8000/docs

Endpoints:
    GET  /health           → Check if API is running
    GET  /providers        → List all LLM providers + pricing
    POST /extract          → Extract structured data from text
    POST /extract/file     → Extract from uploaded .txt file
    GET  /results          → Get all past extraction results
    GET  /results/{doc_id} → Get single extraction result
"""

import os
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from fastapi.responses import FileResponse

from config import (
    PROVIDER_PRICING,
    ACTIVE_PROVIDER,
    calculate_cost,
    get_active_provider
)
from extractor import extract
from validator import validate
from confidence import score
from schemas.invoice import Invoice
from schemas.resume import Resume
from schemas.email import Email


# ─────────────────────────────────────────────
# APP INITIALIZATION
# ─────────────────────────────────────────────

app = FastAPI(
    title="Docstract - Intelligent Document Processor",
    description="""
    Extract structured data from unstructured documents using LLMs.

    Supports:
    - **Invoices** → vendor, amounts, line items, GSTIN
    - **Resumes** → name, skills, experience, education
    - **Emails** → sender, subject, key points, action items

    Built by Ankur Sharma | Gen AI Engineer
    """,
    version="1.0.0"
)

# ── CORS Middleware ───────────────────────────────────────────────────
# Allows your React frontend to call this API.
# Without this, browsers block cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # In production: specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# SCHEMA REGISTRY
# Maps document type string → Pydantic schema class
# ─────────────────────────────────────────────

SCHEMA_REGISTRY = {
    "invoice": Invoice,
    "resume":  Resume,
    "email":   Email
}


# ─────────────────────────────────────────────
# REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────────

class ExtractRequest(BaseModel):
    """Request body for text-based extraction."""
    document: str
    doc_type: str            # "invoice", "resume", or "email"
    doc_id:   Optional[str] = None


class ExtractionResult(BaseModel):
    """Standard response for all extraction results."""
    success:     bool
    doc_type:    str
    doc_id:      str
    timestamp:   str
    extraction:  Optional[dict]  = None
    validation:  Optional[dict]  = None
    confidence:  Optional[dict]  = None
    token_usage: Optional[dict]  = None
    cost_usd:    Optional[float] = None
    provider:    Optional[str]   = None
    error:       Optional[str]   = None


# ─────────────────────────────────────────────
# HELPER: Run full pipeline on raw text
# ─────────────────────────────────────────────

def run_pipeline(raw_text: str, doc_type: str, doc_id: str) -> dict:
    """
    Run the full extraction pipeline on a document.

    Flow:
        raw text → extract → validate → confidence score → return

    Args:
        raw_text (str): Document content
        doc_type (str): "invoice", "resume", or "email"
        doc_id   (str): Unique identifier for this document

    Returns:
        dict: Full pipeline result
    """

    # ── Validate doc_type ─────────────────────────────────────────────
    if doc_type not in SCHEMA_REGISTRY:
        return {
            "success":   False,
            "doc_type":  doc_type,
            "doc_id":    doc_id,
            "timestamp": datetime.now().isoformat(),
            "error":     f"Invalid doc_type '{doc_type}'. "
                         f"Must be one of: {list(SCHEMA_REGISTRY.keys())}"
        }

    schema = SCHEMA_REGISTRY[doc_type]

    result = {
        "success":     False,
        "doc_type":    doc_type,
        "doc_id":      doc_id,
        "timestamp":   datetime.now().isoformat(),
        "extraction":  None,
        "validation":  None,
        "confidence":  None,
        "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "cost_usd":    0.0,
        "provider":    ACTIVE_PROVIDER,
        "error":       None
    }

    # ── Step 1: Extract ───────────────────────────────────────────────
    # extractor.py always returns a tuple (data, token_usage)
    extracted, token_usage = extract(raw_text, schema, doc_id=doc_id)

    result["token_usage"] = token_usage
    result["cost_usd"]    = calculate_cost(
        token_usage.get("prompt_tokens",     0),
        token_usage.get("completion_tokens", 0)
    )

    if extracted is None:
        result["error"] = "Extraction failed - LLM could not parse document"
        return result

    result["extraction"] = json.loads(extracted.model_dump_json())

    # ── Step 2: Validate ──────────────────────────────────────────────
    validation_report    = validate(extracted)
    result["validation"] = validation_report

    # ── Step 3: Confidence scoring ────────────────────────────────────
    confidence_report    = score(extracted)
    result["confidence"] = confidence_report

    result["success"] = True
    return result


# ─────────────────────────────────────────────
# ENDPOINT 1: Health Check
# ─────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    """
    Check if the API is running.

    Returns basic info about the active provider and model.
    Use this to verify the API is up before sending documents.
    """
    provider = get_active_provider()
    return {
        "status":    "healthy",
        "version":   "1.0.0",
        "provider":  provider["name"],
        "model":     provider["model"],
        "free_tier": provider["free"],
        "timestamp": datetime.now().isoformat()
    }


# ─────────────────────────────────────────────
# ENDPOINT 2: List Providers
# ─────────────────────────────────────────────

@app.get("/providers", tags=["System"])
def list_providers():
    """
    List all available LLM providers and their pricing.

    Shows the active provider and cost comparison across all providers.
    Use this to decide which provider to use for your use case.
    """
    providers = []
    for key, info in PROVIDER_PRICING.items():
        providers.append({
            "key":                key,
            "name":               info["name"],
            "model":              info["model"],
            "input_cost_per_1m":  info["input"],
            "output_cost_per_1m": info["output"],
            "free":               info["free"],
            "active":             key == ACTIVE_PROVIDER
        })

    return {
        "active_provider": ACTIVE_PROVIDER,
        "providers":       providers
    }


# ─────────────────────────────────────────────
# ENDPOINT 3: Extract from Text
# ─────────────────────────────────────────────

@app.post("/extract", response_model=ExtractionResult, tags=["Extraction"])
def extract_from_text(request: ExtractRequest):
    """
    Extract structured data from raw text.

    Send a document as plain text and get back structured JSON
    with validation results and confidence scores.

    **doc_type options:** invoice, resume, email

    **Example request body:**
    ```json
    {
        "document": "Invoice from Acme Corp...",
        "doc_type": "invoice",
        "doc_id":   "inv_001"
    }
    ```
    """
    if not request.document.strip():
        raise HTTPException(
            status_code=400,
            detail="Document cannot be empty"
        )

    doc_id = (
        request.doc_id or
        f"{request.doc_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    result = run_pipeline(request.document, request.doc_type, doc_id)

    if not result["success"] and result.get("error"):
        raise HTTPException(
            status_code=422,
            detail=result["error"]
        )

    return result


# ─────────────────────────────────────────────
# ENDPOINT 4: Extract from File Upload
# ─────────────────────────────────────────────

@app.post("/extract/file", response_model=ExtractionResult, tags=["Extraction"])
async def extract_from_file(
    file:     UploadFile = File(...),
    doc_type: str        = Form(...)
):
    """
    Extract structured data from an uploaded .txt file.

    Upload a .txt file and specify the document type.
    Useful for frontend file drag-and-drop functionality.

    **Supported file types:** .txt (PDF support coming soon)
    **doc_type options:** invoice, resume, email
    """

    if not file.filename.endswith(".txt"):
        raise HTTPException(
            status_code=400,
            detail="Only .txt files supported. PDF support coming soon."
        )

    content = await file.read()
    try:
        raw_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File encoding not supported. Please use UTF-8 encoded .txt files."
        )

    if not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty"
        )

    doc_id = file.filename.replace(".txt", "")
    result = run_pipeline(raw_text, doc_type, doc_id)

    if not result["success"] and result.get("error"):
        raise HTTPException(
            status_code=422,
            detail=result["error"]
        )

    return result


# ─────────────────────────────────────────────
# ENDPOINT 5: Get All Past Results
# ─────────────────────────────────────────────

@app.get("/results", tags=["Results"])
def get_all_results():
    """
    Get all past extraction results from the outputs folder.

    Returns a summary of all documents processed so far,
    including validation status, confidence scores, and costs.
    """
    extracted_dir = "outputs/extracted"

    if not os.path.exists(extracted_dir):
        return {
            "total":   0,
            "results": [],
            "message": "No results yet. Run /extract first."
        }

    json_files = [
        f for f in os.listdir(extracted_dir)
        if f.endswith(".json")
    ]

    if not json_files:
        return {
            "total":   0,
            "results": [],
            "message": "No results yet. Run /extract first."
        }

    results = []
    for filename in sorted(json_files):
        filepath = os.path.join(extracted_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        results.append({
            "filename":           data.get("filename"),
            "doc_type":           data.get("doc_type"),
            "status":             data.get("status"),
            "validation_passed":  data.get("validation", {}).get("passed"),
            "avg_confidence":     data.get("confidence", {}).get("avg_confidence"),
            "needs_human_review": data.get("confidence", {}).get("needs_human_review"),
            "total_tokens":       data.get("token_usage", {}).get("total_tokens", 0),
            "cost_usd":           data.get("cost_usd", 0.0),
            "timestamp":          data.get("timestamp")
        })

    return {
        "total":   len(results),
        "results": results
    }


# ─────────────────────────────────────────────
# ENDPOINT 6: Get Single Result
# ─────────────────────────────────────────────

@app.get("/results/{doc_id}", tags=["Results"])
def get_single_result(doc_id: str):
    """
    Get the full extraction result for a specific document.

    Returns everything: extracted fields, validation checks,
    confidence scores per field, token usage, and cost.
    """
    extracted_dir = "outputs/extracted"
    filepath      = os.path.join(extracted_dir, f"{doc_id}_extracted.json")

    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=404,
            detail=f"No result found for doc_id: {doc_id}"
        )

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("Starting Docstract API")
    print("=" * 60)
    print("   Docs:    http://localhost:8000/docs")
    print("   Health:  http://localhost:8000/health")
    print("   Extract: http://localhost:8000/extract")
    print("=" * 60)

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True    # Auto-restarts when you save changes
    )
