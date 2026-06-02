"""
batch_processor.py - Batch Document Processor
Project: Docstract - Intelligent Document Processor
Author: Ankur Sharma

What this does:
    - Archives old extracted files before each run
    - Loops through all documents in sample_documents/
    - Runs extraction, validation, and confidence scoring on each
    - Tracks REAL token usage per document
    - Calculates cost for ANY LLM provider
    - Saves individual JSON results to outputs/extracted/
    - Saves batch summary to outputs/batch_results/
    - Prints a full summary with cost analysis

HOW TO CHANGE MODEL OR PROVIDER:
    Edit config.py only. Change ACTIVE_MODEL and/or ACTIVE_PROVIDER.
    Do NOT change anything in this file.
"""

import os
import json
import csv
from datetime import datetime
from extractor import extract
from validator import validate
from confidence import score
from schemas.invoice import Invoice
from schemas.resume import Resume
from schemas.email import Email

# ── All config comes from config.py ──────────────────────────────────
from config import (
    MODEL,
    ACTIVE_PROVIDER,
    PROVIDER_PRICING,
    ACTIVE_PROVIDER_INFO
)


# ─────────────────────────────────────────────
# DOCUMENT ROUTING
# ─────────────────────────────────────────────

DOCUMENT_TYPES = {
    "invoices": Invoice,
    "resumes":  Resume,
    "emails":   Email
}

SAMPLE_DOCS_DIR = "sample_documents"
EXTRACTED_DIR   = "outputs/extracted"
BATCH_RESULTS   = "outputs/batch_results"
ARCHIVE_DIR     = "outputs/archive"


# ─────────────────────────────────────────────
# HELPER: Calculate cost using active provider
# ─────────────────────────────────────────────

def calculate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate USD cost using the active provider's pricing from config.py.

    Args:
        prompt_tokens (int): Input token count
        completion_tokens (int): Output token count

    Returns:
        float: Estimated cost in USD
    """
    provider = PROVIDER_PRICING[ACTIVE_PROVIDER]

    input_cost  = (prompt_tokens     / 1_000_000) * provider["input"]
    output_cost = (completion_tokens / 1_000_000) * provider["output"]

    return round(input_cost + output_cost, 6)


# ─────────────────────────────────────────────
# HELPER: Calculate cost for any specific provider
# ─────────────────────────────────────────────

def calculate_cost_for_provider(
    prompt_tokens: int,
    completion_tokens: int,
    provider_key: str
) -> float:
    """
    Calculate cost for a SPECIFIC provider (used for comparisons).

    Args:
        prompt_tokens (int): Input token count
        completion_tokens (int): Output token count
        provider_key (str): Key from PROVIDER_PRICING in config.py

    Returns:
        float: Estimated cost in USD
    """
    p = PROVIDER_PRICING.get(provider_key, PROVIDER_PRICING["custom"])

    input_cost  = (prompt_tokens     / 1_000_000) * p["input"]
    output_cost = (completion_tokens / 1_000_000) * p["output"]

    return round(input_cost + output_cost, 6)


# ─────────────────────────────────────────────
# CORE: Process a single document
# ─────────────────────────────────────────────

def process_document(filepath: str, schema) -> dict:
    """
    Run the full pipeline on a single document.

    Pipeline:
        1. Read raw text
        2. Extract structured data (LLM) — captures real token usage
        3. Validate extracted data (business logic)
        4. Score confidence per field
        5. Calculate cost for this document
        6. Save JSON output

    Args:
        filepath (str): Path to the .txt document
        schema: Pydantic schema class to extract into

    Returns:
        dict: Full processing result including token_usage and cost
    """
    filename = os.path.basename(filepath)
    doc_type = filepath.split(os.sep)[-2]

    print(f"\n{'='*60}")
    print(f"📄 Processing: {filename}")
    print(f"   Type: {doc_type}  |  Model: {MODEL}")
    print(f"{'='*60}")

    result = {
        "filename":    filename,
        "doc_type":    doc_type,
        "filepath":    filepath,
        "timestamp":   datetime.now().isoformat(),
        "model":       MODEL,              # logged per document
        "provider":    ACTIVE_PROVIDER,    # logged per document
        "status":      "failed",
        "extraction":  None,
        "validation":  None,
        "confidence":  None,
        "token_usage": {
            "prompt_tokens":     0,
            "completion_tokens": 0,
            "total_tokens":      0
        },
        "cost_usd":    0.0,
        "error":       None
    }

    # ── Step 1: Read raw text ─────────────────────────────────────────
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw_text = f.read()
    except Exception as e:
        result["error"] = f"File read error: {str(e)}"
        print(f"   ❌ Could not read file: {e}")
        return result

    # ── Step 2: Extract ───────────────────────────────────────────────
    print(f"\n🔍 Extracting...")
    extracted = extract(raw_text, schema, doc_id=filename)

    result["token_usage"] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    result["cost_usd"]    = 0.0

    if extracted is None:
        result["error"] = "Extraction failed"
        print(f"   ❌ Extraction failed")
        return result

    result["extraction"] = json.loads(extracted.model_dump_json())

    # ── Step 3: Validate ──────────────────────────────────────────────
    print(f"\n✅ Validating...")
    validation_report    = validate(extracted)
    result["validation"] = validation_report

    verdict = "✅ PASSED" if validation_report["passed"] else "❌ FAILED"
    print(f"   Validation: {verdict} "
          f"({validation_report['passed_checks']}/{validation_report['total_checks']} checks)")

    # ── Step 4: Confidence scoring ────────────────────────────────────
    print(f"\n📊 Scoring confidence...")
    confidence_report    = score(extracted)
    result["confidence"] = confidence_report

    print(f"   Average confidence: {confidence_report['avg_confidence']}%")
    if confidence_report["needs_human_review"]:
        flagged = list(confidence_report["flagged_fields"].keys())
        print(f"   ⚠️  Flagged for review: {', '.join(flagged)}")

    # ── Step 5: Show cost for this document ───────────────────────────
    if ACTIVE_PROVIDER_INFO["free"]:
        print(f"\n💰 Cost: $0.00 (free tier)")
    else:
        print(f"\n💰 Cost: ${result['cost_usd']:.6f} [{ACTIVE_PROVIDER_INFO['name']}]")

    # ── Step 6: Save JSON output ──────────────────────────────────────
    os.makedirs(EXTRACTED_DIR, exist_ok=True)
    output_filename = filename.replace(".txt", "_extracted.json")
    output_path     = os.path.join(EXTRACTED_DIR, output_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\n   💾 Saved to: {output_path}")
    result["status"] = "success"

    return result


# ─────────────────────────────────────────────
# CORE: Run batch processing
# ─────────────────────────────────────────────

def run_batch() -> list[dict]:
    """
    Process all documents in sample_documents/ folder.

    Returns:
        list[dict]: List of all processing results
    """
    all_results = []

    print("\n" + "="*60)
    print("🚀 STARTING BATCH PROCESSING")
    print("="*60)

    # Show which model and provider are active (both from config.py)
    print(f"Model    : {MODEL}")
    print(f"Provider : {ACTIVE_PROVIDER_INFO['name']}")
    if ACTIVE_PROVIDER_INFO["free"]:
        print(f"Pricing  : Free tier")
    else:
        print(f"Pricing  : ${ACTIVE_PROVIDER_INFO['input']}/1M input, "
              f"${ACTIVE_PROVIDER_INFO['output']}/1M output tokens")
    print(f"\nTo change model or provider → edit config.py")

    # ── Archive old extracted JSONs before fresh run ──────────────────
    if os.path.exists(EXTRACTED_DIR):
        old_files = [
            f for f in os.listdir(EXTRACTED_DIR)
            if f.endswith(".json")
        ]
        if old_files:
            archive_folder = (
                f"{ARCHIVE_DIR}/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            os.makedirs(archive_folder, exist_ok=True)
            for old_file in old_files:
                os.rename(
                    os.path.join(EXTRACTED_DIR, old_file),
                    os.path.join(archive_folder, old_file)
                )
            print(f"\n📦 Archived {len(old_files)} old file(s) to: {archive_folder}")

    print(f"\nScanning: {SAMPLE_DOCS_DIR}/")

    # ── Loop through each document type ──────────────────────────────
    for doc_type, schema in DOCUMENT_TYPES.items():
        folder = os.path.join(SAMPLE_DOCS_DIR, doc_type)

        if not os.path.exists(folder):
            print(f"\n⚠️  Folder not found: {folder}")
            continue

        txt_files = [
            f for f in os.listdir(folder)
            if f.endswith(".txt")
        ]

        if not txt_files:
            print(f"\n⚠️  No .txt files found in {folder}")
            continue

        print(f"\n📁 {doc_type.upper()}: Found {len(txt_files)} file(s)")

        for filename in sorted(txt_files):
            filepath = os.path.join(folder, filename)
            result   = process_document(filepath, schema)
            all_results.append(result)

    return all_results


# ─────────────────────────────────────────────
# HELPER: Save batch results to CSV
# ─────────────────────────────────────────────

def save_batch_csv(results: list[dict]):
    """Save a summary of all results to CSV including token and cost data."""

    os.makedirs(BATCH_RESULTS, exist_ok=True)
    csv_path = (
        f"{BATCH_RESULTS}/batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow([
            "filename",
            "doc_type",
            "model",
            "provider",
            "status",
            "validation_passed",
            "checks_passed",
            "total_checks",
            "avg_confidence",
            "needs_human_review",
            "flagged_fields",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cost_usd",
            "timestamp"
        ])

        for r in results:
            validation  = r.get("validation") or {}
            confidence  = r.get("confidence") or {}
            token_usage = r.get("token_usage") or {}

            writer.writerow([
                r["filename"],
                r["doc_type"],
                r.get("model", MODEL),
                r.get("provider", ACTIVE_PROVIDER),
                r["status"],
                validation.get("passed", "N/A"),
                validation.get("passed_checks", "N/A"),
                validation.get("total_checks", "N/A"),
                confidence.get("avg_confidence", "N/A"),
                confidence.get("needs_human_review", "N/A"),
                ", ".join(confidence.get("flagged_fields", {}).keys()),
                token_usage.get("prompt_tokens", 0),
                token_usage.get("completion_tokens", 0),
                token_usage.get("total_tokens", 0),
                r.get("cost_usd", 0.0),
                r["timestamp"]
            ])

    print(f"\n💾 Batch CSV saved to: {csv_path}")
    return csv_path


# ─────────────────────────────────────────────
# HELPER: Print final summary
# ─────────────────────────────────────────────

def print_summary(results: list[dict]):
    """Print a clean summary with real token and cost data."""

    total      = len(results)
    successful = sum(1 for r in results if r["status"] == "success")
    failed     = total - successful

    validation_passed = sum(
        1 for r in results
        if r.get("validation", {}) and r["validation"].get("passed")
    )

    needs_review = sum(
        1 for r in results
        if r.get("confidence", {}) and r["confidence"].get("needs_human_review")
    )

    avg_confidence = round(
        sum(
            r["confidence"]["avg_confidence"]
            for r in results
            if r.get("confidence")
        ) / max(successful, 1), 1
    )

    # ── Token aggregation ─────────────────────────────────────────────
    total_prompt_tokens     = sum(
        r.get("token_usage", {}).get("prompt_tokens", 0)
        for r in results
    )
    total_completion_tokens = sum(
        r.get("token_usage", {}).get("completion_tokens", 0)
        for r in results
    )
    total_tokens = sum(
        r.get("token_usage", {}).get("total_tokens", 0)
        for r in results
    )
    total_cost   = sum(r.get("cost_usd", 0.0) for r in results)
    cost_per_doc = round(total_cost / max(successful, 1), 6)

    # Scale projections
    cost_per_1000  = round(cost_per_doc * 1000, 4)
    cost_per_10000 = round(cost_per_doc * 10000, 2)

    print("\n" + "="*60)
    print("📊 BATCH PROCESSING SUMMARY")
    print("="*60)
    print(f"Total documents        : {total}")
    print(f"Successfully processed : {successful}")
    print(f"Failed                 : {failed}")
    print(f"Validation passed      : {validation_passed}/{successful}")
    print(f"Needs human review     : {needs_review}/{successful}")
    print(f"Avg confidence         : {avg_confidence}%")
    print(f"{'─'*60}")
    print(f"Model                  : {MODEL}")
    print(f"Total tokens used      : {total_tokens:,}")
    print(f"  Prompt tokens        : {total_prompt_tokens:,}")
    print(f"  Completion tokens    : {total_completion_tokens:,}")
    print(f"{'─'*60}")

    # ── Cost section changes based on active provider ─────────────────
    print(f"Provider               : {ACTIVE_PROVIDER_INFO['name']}")

    if ACTIVE_PROVIDER_INFO["free"]:
        print(f"Cost this run          : $0.00 (free tier)")
        print(f"Cost per document      : $0.00 (free tier)")
        print(f"")
        print(f"  Estimated cost if using paid providers:")
        print(f"  {'─'*40}")
        for key, p in PROVIDER_PRICING.items():
            if not p["free"] and key != "custom":
                run_cost = calculate_cost_for_provider(
                    total_prompt_tokens,
                    total_completion_tokens,
                    key
                )
                doc_cost = round(run_cost / max(successful, 1), 6)
                print(f"  {p['name']:<35} ${run_cost:.4f} total  "
                      f"(${doc_cost:.6f}/doc)")
    else:
        print(f"Cost this run          : ${total_cost:.6f}")
        print(f"Cost per document      : ${cost_per_doc:.6f}")
        print(f"Cost per 1,000 docs    : ${cost_per_1000:.4f}")
        print(f"Cost per 10,000 docs   : ${cost_per_10000:.2f}")

    # ── Per document table ────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"{'File':<25} {'Type':<10} {'Valid':<8} {'Conf':<8} "
          f"{'Tokens':<8} {'Review'}")
    print(f"{'─'*60}")

    for r in results:
        if r["status"] == "success":
            valid  = "✅" if r["validation"]["passed"] else "❌"
            conf   = f"{r['confidence']['avg_confidence']}%"
            tokens = str(r.get("token_usage", {}).get("total_tokens", 0))
            review = "⚠️  Yes" if r["confidence"]["needs_human_review"] else "✅ No"
            print(f"{r['filename']:<25} {r['doc_type']:<10} {valid:<8} "
                  f"{conf:<8} {tokens:<8} {review}")
        else:
            print(f"{r['filename']:<25} {r['doc_type']:<10} ❌ FAILED")

    print("="*60)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    results = run_batch()
    print_summary(results)
    save_batch_csv(results)
