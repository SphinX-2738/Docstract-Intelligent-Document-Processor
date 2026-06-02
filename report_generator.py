"""
report_generator.py - Report Generator
Project: Docstract - Intelligent Document Processor
Author: Ankur Sharma

What this does:
    - Reads the latest batch results CSV
    - Reads all extracted JSON files
    - Generates a comprehensive terminal report
    - Saves exact terminal output to outputs/reports/
    - Shows per-document breakdown with all scores
    - Gives actionable recommendations
"""

import os
import json
import csv
import sys
from datetime import datetime


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

EXTRACTED_DIR = "outputs/extracted"
BATCH_RESULTS = "outputs/batch_results"
REPORTS_DIR   = "outputs/reports"


# ─────────────────────────────────────────────
# HELPER: Tee output to terminal and file
# ─────────────────────────────────────────────

class Tee:
    """Write to both terminal and file simultaneously."""
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()


# ─────────────────────────────────────────────
# HELPER: Load latest batch CSV
# ─────────────────────────────────────────────

def load_latest_csv() -> list[dict]:
    """Load the most recent batch results CSV."""

    if not os.path.exists(BATCH_RESULTS):
        print("❌ No batch results found. Run batch_processor.py first.")
        return []

    csv_files = sorted([
        f for f in os.listdir(BATCH_RESULTS)
        if f.endswith(".csv")
    ])

    if not csv_files:
        print("❌ No CSV files found. Run batch_processor.py first.")
        return []

    latest = os.path.join(BATCH_RESULTS, csv_files[-1])
    print(f"📂 Loading: {latest}")

    rows = []
    with open(latest, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    return rows


# ─────────────────────────────────────────────
# HELPER: Load all extracted JSONs
# ─────────────────────────────────────────────

def load_extracted_jsons() -> list[dict]:
    """Load all extracted JSON files from outputs/extracted/"""

    if not os.path.exists(EXTRACTED_DIR):
        return []

    json_files = [
        f for f in os.listdir(EXTRACTED_DIR)
        if f.endswith(".json")
    ]

    results = []
    for filename in sorted(json_files):
        filepath = os.path.join(EXTRACTED_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            results.append(json.load(f))

    return results


# ─────────────────────────────────────────────
# REPORT: Overall summary
# ─────────────────────────────────────────────

def print_overall_summary(rows: list[dict]):
    """Print overall batch statistics."""

    total             = len(rows)
    successful        = sum(1 for r in rows if r["status"] == "success")
    failed            = total - successful
    validation_passed = sum(1 for r in rows if r["validation_passed"] == "True")
    needs_review      = sum(1 for r in rows if r["needs_human_review"] == "True")

    confidences = [
        float(r["avg_confidence"])
        for r in rows
        if r["avg_confidence"] not in ("N/A", "")
    ]
    avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0

    print("\n" + "=" * 65)
    print("📊 DOCSTRACT — INTELLIGENT DOCUMENT PROCESSOR")
    print("   Batch Processing Report")
    print(f"   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    print(f"\n{'─' * 65}")
    print("OVERALL STATISTICS")
    print(f"{'─' * 65}")
    print(f"  Total documents processed : {total}")
    print(f"  Successfully extracted    : {successful}")
    print(f"  Failed extractions        : {failed}")
    print(f"  Validation passed         : {validation_passed}/{total}")
    print(f"  Flagged for human review  : {needs_review}/{total}")
    print(f"  Average confidence        : {avg_confidence}%")


# ─────────────────────────────────────────────
# REPORT: Per document breakdown
# ─────────────────────────────────────────────

def print_per_document(rows: list[dict]):
    """Print per-document breakdown table."""

    print(f"\n{'─' * 65}")
    print("PER-DOCUMENT BREAKDOWN")
    print(f"{'─' * 65}")
    print(f"{'File':<25} {'Type':<10} {'Valid':<8} {'Conf':<8} {'Review'}")
    print(f"{'─' * 65}")

    for r in rows:
        valid  = "✅ Yes" if r["validation_passed"] == "True" else "❌ No"
        conf   = f"{r['avg_confidence']}%" if r["avg_confidence"] not in ("N/A", "") else "N/A"
        review = "⚠️  Yes" if r["needs_human_review"] == "True" else "✅ No"
        status = "" if r["status"] == "success" else " [FAILED]"
        print(f"{r['filename']:<25} {r['doc_type']:<10} {valid:<8} {conf:<8} {review}{status}")


# ─────────────────────────────────────────────
# REPORT: Per document field scores
# ─────────────────────────────────────────────

def print_field_scores(results: list[dict]):
    """Print confidence scores per field for each document."""

    print(f"\n{'─' * 65}")
    print("FIELD-LEVEL CONFIDENCE SCORES")
    print(f"{'─' * 65}")

    for r in results:
        if not r.get("confidence"):
            continue

        status_label = "" if r["status"] == "success" else " ⚠️  [validation failed]"
        print(f"\n📄 {r['filename']} ({r['doc_type']}){status_label}")
        print()

        confidence   = r.get("confidence", {})
        field_scores = confidence.get("field_scores", {})

        if not field_scores:
            print("   No field scores available")
            continue

        for field, score_val in field_scores.items():
            flag = "⚠️ " if score_val < 70 else "✅"
            bar  = "█" * (score_val // 10) + "░" * (10 - score_val // 10)
            print(f"   {flag} {field:<20} {bar} {score_val}%")
            print()


# ─────────────────────────────────────────────
# REPORT: Flagged fields
# ─────────────────────────────────────────────

def print_flagged_fields(results: list[dict]):
    """Print all fields flagged for human review."""

    print(f"\n{'─' * 65}")
    print("⚠️  FIELDS FLAGGED FOR HUMAN REVIEW")
    print(f"{'─' * 65}")

    any_flagged = False

    for r in results:
        if not r.get("confidence"):
            continue

        confidence = r.get("confidence", {})
        flagged    = confidence.get("flagged_fields", {})

        if flagged:
            any_flagged = True
            print(f"\n📄 {r['filename']}:")
            for field, score_val in flagged.items():
                print(f"   ⚠️  {field}: {score_val}% confidence — needs manual verification")

    if not any_flagged:
        print("   ✅ No fields flagged for review!")


# ─────────────────────────────────────────────
# REPORT: Recommendations
# ─────────────────────────────────────────────

def print_recommendations(results: list[dict]):
    """Generate actionable recommendations based on results."""

    print(f"\n{'─' * 65}")
    print("💡 RECOMMENDATIONS")
    print(f"{'─' * 65}")

    recommendations = []

    for r in results:
        if not r.get("confidence"):
            continue

        confidence = r.get("confidence", {})
        flagged    = confidence.get("flagged_fields", {})
        validation = r.get("validation", {})
        doc_type   = r["doc_type"]
        filename   = r["filename"]

        if doc_type == "invoices" and "invoice_number" in flagged:
            recommendations.append(
                f"[WARN] {filename}: No invoice number found. "
                f"Ask sender to include invoice number for tracking."
            )

        if "date" in flagged:
            recommendations.append(
                f"[WARN] {filename}: No date found. "
                f"Date is important for payment tracking and compliance."
            )

        avg = confidence.get("avg_confidence", 100)
        if avg < 60:
            recommendations.append(
                f"[CRIT] {filename}: Low confidence ({avg}%). "
                f"Manual review strongly recommended."
            )

        if validation and not validation.get("passed"):
            failed_checks = [
                c["check"] for c in validation.get("checks", [])
                if not c["passed"]
            ]
            recommendations.append(
                f"[FIX] {filename}: Validation failed on: {', '.join(failed_checks)}"
            )

        if doc_type == "emails" and "body" in flagged:
            recommendations.append(
                f"[FIX] {filename}: Email body not extracted. "
                f"Consider improving extraction prompt for emails."
            )

    if recommendations:
        for rec in recommendations:
            print(f"\n  {rec}")
    else:
        print("  ✅ No recommendations — all documents processed cleanly!")


# ─────────────────────────────────────────────
# REPORT: Cost analysis
# ─────────────────────────────────────────────

def print_cost_analysis(results: list[dict]):
    """Print token usage and cost estimates."""

    print(f"\n{'─' * 65}")
    print("💰 COST ANALYSIS")
    print(f"{'─' * 65}")

    total_docs            = len([r for r in results if r.get("confidence")])
    estimated_tokens      = total_docs * 800
    estimated_cost_openai = (estimated_tokens / 1_000_000) * 0.15

    print(f"  Documents processed       : {total_docs}")
    print(f"  Estimated tokens used     : ~{estimated_tokens:,}")
    print(f"  Estimated cost (OpenAI)   : ${estimated_cost_openai:.4f}")
    print(f"  Actual cost (Groq)        : $0.0000 (free tier)")
    print(f"\n  NOTE: Groq is free tier. Figures above show")
    print(f"  production cost reference using OpenAI pricing.")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":

    rows    = load_latest_csv()
    results = load_extracted_jsons()

    if not rows:
        exit()

    # Set up report file
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(
        REPORTS_DIR,
        f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )

    # Tee output to both terminal and file simultaneously
    with open(report_path, "w", encoding="utf-8") as report_file:
        sys.stdout = Tee(sys.__stdout__, report_file)

        print_overall_summary(rows)
        print_per_document(rows)
        print_field_scores(results)
        print_flagged_fields(results)
        print_recommendations(results)
        print_cost_analysis(results)

        print(f"\n{'=' * 65}")
        print("Report complete.")
        print("=" * 65)

        sys.stdout = sys.__stdout__

    print(f"\n💾 Report saved to: {report_path}")
