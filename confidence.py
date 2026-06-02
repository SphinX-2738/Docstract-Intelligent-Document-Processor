"""
confidence.py - Confidence Scoring System
Project: Docstract - Intelligent Document Processor
Author: Ankur Sharma

What this does:
    - Takes a validated Pydantic object as input
    - Scores each field from 0-100 based on local signals
    - Flags fields below threshold for human review
    - Returns a confidence report

Why this matters:
    Even when extraction succeeds, some fields are more
    reliable than others. Confidence scoring tells downstream
    systems which fields to trust and which need human review.
"""

from schemas.invoice import Invoice
from schemas.resume import Resume
from schemas.email import Email
from pydantic import BaseModel

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

CONFIDENCE_THRESHOLD = 70  # Fields below this need human review


# ─────────────────────────────────────────────
# HELPER: Score a single field
# ─────────────────────────────────────────────

def score_field(value, field_type: str = "str") -> int:
    """
    Score a single field based on local signals.

    Scoring logic:
        - None/null/empty → 0
        - Present but minimal → 50
        - Present and non-empty string → 70
        - Present with format validation → 80-100

    Args:
        value: The field value
        field_type: "str", "float", "int", "list", "gstin"

    Returns:
        int: Confidence score 0-100
    """
    # None or empty = zero confidence
    if value is None:
        return 0

    if field_type == "str":
        if not isinstance(value, str) or not value.strip():
            return 0
        # longer strings are more likely to be real extractions
        if len(value.strip()) >= 3:
            return 80
        return 50

    elif field_type == "float":
        if not isinstance(value, (int, float)):
            return 0
        if value > 0:
            return 90
        return 30  # zero amounts are suspicious

    elif field_type == "int":
        if not isinstance(value, int):
            return 0
        if value > 0:
            return 90
        return 30

    elif field_type == "list":
        if not isinstance(value, list):
            return 0
        if len(value) == 0:
            return 30  # empty list is suspicious
        return 90

    elif field_type == "gstin":
        if not isinstance(value, str):
            return 0
        clean = value.replace(" ", "")
        if len(clean) == 15:
            return 95  # correct format
        return 40  # wrong format

    return 50  # default


# ─────────────────────────────────────────────
# INVOICE CONFIDENCE SCORER
# ─────────────────────────────────────────────

def score_invoice(invoice: Invoice) -> dict:
    """Score confidence for each field in an Invoice."""

    field_scores = {
        "invoice_number":  score_field(invoice.invoice_number, "str"),
        "date":            score_field(invoice.date, "str"),
        "sender_company":  score_field(invoice.sender_company, "str"),
        "receiver_company": score_field(invoice.receiver_company, "str"),
        "line_items":      score_field(invoice.line_items, "list"),
        "subtotal":        score_field(invoice.subtotal, "float"),
        "total_amount":    score_field(invoice.total_amount, "float"),
        "gstin_sender":    score_field(invoice.gstin_sender, "gstin"),
        "phone":           score_field(invoice.phone, "str"),
        "email":           score_field(invoice.email, "str"),
        "due_date":        score_field(invoice.due_date, "str"),
    }

    return build_confidence_report(field_scores)


# ─────────────────────────────────────────────
# RESUME CONFIDENCE SCORER
# ─────────────────────────────────────────────

def score_resume(resume: Resume) -> dict:
    """Score confidence for each field in a Resume."""

    field_scores = {
        "name":             score_field(resume.name, "str"),
        "email":            score_field(resume.email, "str"),
        "phone":            score_field(resume.phone, "str"),
        "technical_skills": score_field(resume.technical_skills, "list"),
        "work_experience":  score_field(resume.work_experience, "list"),
        "education":        score_field(resume.education, "list"),
        "projects":         score_field(resume.projects, "list"),
    }

    return build_confidence_report(field_scores)


# ─────────────────────────────────────────────
# EMAIL CONFIDENCE SCORER
# ─────────────────────────────────────────────

def score_email(email: Email) -> dict:
    """Score confidence for each field in an Email."""

    field_scores = {
        "sender_name":   score_field(email.sender_name, "str"),
        "receiver_name": score_field(email.receiver_name, "str"),
        "subject":       score_field(email.subject, "str"),
        "date":          score_field(email.date, "str"),
        "body":          score_field(email.body, "str"),
        "key_points":    score_field(email.key_points, "list"),
        "action_items":  score_field(email.action_items, "list"),
    }

    return build_confidence_report(field_scores)


# ─────────────────────────────────────────────
# HELPER: Build confidence report
# ─────────────────────────────────────────────

def build_confidence_report(field_scores: dict) -> dict:
    """
    Build a confidence report from field scores.

    Args:
        field_scores: dict of field_name -> score (0-100)

    Returns:
        dict: Full confidence report with averages and flags
    """
    avg_confidence = round(sum(field_scores.values()) / len(field_scores), 1)

    # Flag fields below threshold for human review
    flagged_fields = {
        field: score
        for field, score in field_scores.items()
        if score < CONFIDENCE_THRESHOLD
    }

    needs_human_review = len(flagged_fields) > 0

    return {
        "avg_confidence": avg_confidence,
        "needs_human_review": needs_human_review,
        "flagged_fields": flagged_fields,
        "field_scores": field_scores
    }


# ─────────────────────────────────────────────
# MAIN SCORER - Routes to correct scorer
# ─────────────────────────────────────────────

def score(extracted_data: BaseModel) -> dict:
    """
    Route to the correct scorer based on data type.

    Args:
        extracted_data: A validated Pydantic object

    Returns:
        dict: Confidence report
    """
    if isinstance(extracted_data, Invoice):
        return score_invoice(extracted_data)
    elif isinstance(extracted_data, Resume):
        return score_resume(extracted_data)
    elif isinstance(extracted_data, Email):
        return score_email(extracted_data)
    else:
        return {"avg_confidence": 0, "needs_human_review": True, "flagged_fields": {}, "field_scores": {}}


# ─────────────────────────────────────────────
# ENTRY POINT - Test confidence scorer
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from extractor import extract
    from schemas.invoice import Invoice

    with open("sample_documents/invoices/invoice_001.txt", "r") as f:
        raw_text = f.read()

    print("=" * 60)
    print("Testing confidence scorer on invoice_001.txt")
    print("=" * 60)

    extracted = extract(raw_text, Invoice)

    if extracted:
        print("\n📊 CONFIDENCE SCORES:")
        print("-" * 60)
        report = score(extracted)

        for field, confidence in report["field_scores"].items():
            flag = "⚠️  REVIEW" if confidence < CONFIDENCE_THRESHOLD else "✅"
            print(f"   {flag} {field}: {confidence}%")

        print(f"\n📈 Average confidence: {report['avg_confidence']}%")
        print(f"🔍 Needs human review: {report['needs_human_review']}")

        if report["flagged_fields"]:
            print(f"\n⚠️  FLAGGED FOR REVIEW:")
            for field, score_val in report["flagged_fields"].items():
                print(f"   - {field}: {score_val}%")