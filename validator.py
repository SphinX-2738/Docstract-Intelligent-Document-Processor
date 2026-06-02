"""
validator.py - Business Logic Validation Layer
Project: Docstract - Intelligent Document Processor
Author: Ankur Sharma

What this does:
    - Takes a Pydantic-validated object as input
    - Runs business logic checks beyond type validation
    - Returns a validation report with pass/fail and issues found

Why this exists:
    Pydantic only checks types and required fields.
    Business logic like "does subtotal + tax = total" 
    requires custom validation logic.
"""

from schemas.invoice import Invoice
from schemas.resume import Resume
from schemas.email import Email
from pydantic import BaseModel


# ─────────────────────────────────────────────
# HELPER: Build validation report
# ─────────────────────────────────────────────

def build_report(passed: bool, checks: list[dict]) -> dict:
    """
    Build a structured validation report.

    Args:
        passed (bool): Overall pass/fail
        checks (list): List of individual check results

    Returns:
        dict: Validation report
    """
    return {
        "passed": passed,
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c["passed"]),
        "failed_checks": sum(1 for c in checks if not c["passed"]),
        "checks": checks
    }


def add_check(checks: list, name: str, passed: bool, message: str):
    """Add a single check result to the checks list."""
    checks.append({
        "check": name,
        "passed": passed,
        "message": message
    })
    status = "✅" if passed else "❌"
    print(f"   {status} {name}: {message}")


# ─────────────────────────────────────────────
# INVOICE VALIDATOR
# ─────────────────────────────────────────────

def validate_invoice(invoice: Invoice) -> dict:
    """
    Run business logic validation on extracted Invoice data.

    Checks:
        1. Total amount is positive
        2. At least one line item exists
        3. Line item amounts are positive
        4. Subtotal + tax roughly equals total
        5. GSTIN format is valid (15 characters)
        6. Sender and receiver company names are not empty
    """
    checks = []

    # Check 1: Total amount is positive
    add_check(
        checks,
        "Total amount positive",
        invoice.total_amount > 0,
        f"Total amount: ₹{invoice.total_amount}"
    )

    # Check 2: At least one line item
    add_check(
        checks,
        "Has line items",
        len(invoice.line_items) > 0,
        f"Found {len(invoice.line_items)} line item(s)"
    )

    # Check 3: Line item amounts are positive
    if invoice.line_items:
        all_positive = all(item.amount > 0 for item in invoice.line_items)
        add_check(
            checks,
            "Line item amounts positive",
            all_positive,
            "All line item amounts are positive" if all_positive else "Some line items have zero or negative amounts"
        )

    # Check 4: Math check — subtotal + tax ≈ total
    # We allow 1% tolerance because of rounding differences
    if invoice.subtotal and invoice.total_amount:
        tax_amount = (invoice.igst or 0) + (invoice.cgst or 0) + (invoice.sgst or 0) + (invoice.gst or 0)
        calculated_total = invoice.subtotal + tax_amount
        tolerance = invoice.total_amount * 0.01  # 1% tolerance
        math_valid = abs(calculated_total - invoice.total_amount) <= tolerance
        add_check(
            checks,
            "Math check (subtotal + tax = total)",
            math_valid,
            f"Subtotal ₹{invoice.subtotal} + Tax ₹{tax_amount} = ₹{calculated_total} (Expected: ₹{invoice.total_amount})"
        )

    # Check 5: GSTIN format (must be 15 characters)
    if invoice.gstin_sender:
        gstin_valid = len(invoice.gstin_sender.replace(" ", "")) == 15
        add_check(
            checks,
            "GSTIN format valid",
            gstin_valid,
            f"GSTIN: {invoice.gstin_sender} ({'valid' if gstin_valid else 'invalid - must be 15 characters'})"
        )

    # Check 6: Company names not empty
    sender_valid = bool(invoice.sender_company and invoice.sender_company.strip())
    receiver_valid = bool(invoice.receiver_company and invoice.receiver_company.strip())
    add_check(
        checks,
        "Sender company name present",
        sender_valid,
        f"Sender: {invoice.sender_company}"
    )
    add_check(
        checks,
        "Receiver company name present",
        receiver_valid,
        f"Receiver: {invoice.receiver_company}"
    )

    overall_passed = all(c["passed"] for c in checks)
    return build_report(overall_passed, checks)


# ─────────────────────────────────────────────
# RESUME VALIDATOR
# ─────────────────────────────────────────────

def validate_resume(resume: Resume) -> dict:
    """Run business logic validation on extracted Resume data."""
    checks = []

    # Check 1: Name is present
    add_check(
        checks,
        "Name present",
        bool(resume.name and resume.name.strip()),
        f"Name: {resume.name}"
    )

    # Check 2: At least one contact method
    has_contact = bool(resume.email or resume.phone)
    add_check(
        checks,
        "Has contact information",
        has_contact,
        "Email or phone found" if has_contact else "No contact information found"
    )

    # Check 3: Has at least one skill
    has_skills = len(resume.technical_skills) > 0 or len(resume.tech_stack) > 0
    add_check(
        checks,
        "Has technical skills",
        has_skills,
        f"Found {len(resume.technical_skills)} technical skills"
    )

    # Check 4: Has education
    add_check(
        checks,
        "Has education",
        len(resume.education) > 0,
        f"Found {len(resume.education)} education record(s)"
    )

    overall_passed = all(c["passed"] for c in checks)
    return build_report(overall_passed, checks)


# ─────────────────────────────────────────────
# EMAIL VALIDATOR
# ─────────────────────────────────────────────

def validate_email(email: Email) -> dict:
    """Run business logic validation on extracted Email data."""
    checks = []

    # Check 1: Sender present
    add_check(
        checks,
        "Sender present",
        bool(email.sender_name and email.sender_name.strip()),
        f"Sender: {email.sender_name}"
    )

    # Check 2: Subject present
    add_check(
        checks,
        "Subject present",
        bool(email.subject and email.subject.strip()),
        f"Subject: {email.subject}"
    )

    # Check 3: Body present
    add_check(
        checks,
        "Body present",
        bool(email.body and email.body.strip()),
        f"Body length: {len(email.body) if email.body else 0} characters"
    )

    # Check 4: Has key points or action items
    has_insights = len(email.key_points) > 0 or len(email.action_items) > 0
    add_check(
        checks,
        "Has key points or action items",
        has_insights,
        f"Found {len(email.key_points)} key points and {len(email.action_items)} action items"
    )

    overall_passed = all(c["passed"] for c in checks)
    return build_report(overall_passed, checks)


# ─────────────────────────────────────────────
# MAIN VALIDATOR - Routes to correct validator
# ─────────────────────────────────────────────

def validate(extracted_data: BaseModel) -> dict:
    """
    Route to the correct validator based on data type.

    Args:
        extracted_data: A validated Pydantic object

    Returns:
        dict: Validation report
    """
    if isinstance(extracted_data, Invoice):
        return validate_invoice(extracted_data)
    elif isinstance(extracted_data, Resume):
        return validate_resume(extracted_data)
    elif isinstance(extracted_data, Email):
        return validate_email(extracted_data)
    else:
        return build_report(False, [{"check": "Unknown type", "passed": False, "message": f"Unknown document type: {type(extracted_data)}"}])


# ─────────────────────────────────────────────
# ENTRY POINT - Test the validator
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from extractor import extract
    from schemas.invoice import Invoice

    # Load and extract
    with open("sample_documents/invoices/invoice_001.txt", "r") as f:
        raw_text = f.read()

    print("=" * 60)
    print("Testing validator on invoice_001.txt")
    print("=" * 60)

    extracted = extract(raw_text, Invoice)

    if extracted:
        print("\n📋 RUNNING VALIDATION CHECKS:")
        print("-" * 60)
        report = validate(extracted)

        print("\n📊 VALIDATION SUMMARY:")
        print(f"   Overall: {'✅ PASSED' if report['passed'] else '❌ FAILED'}")
        print(f"   Checks passed: {report['passed_checks']}/{report['total_checks']}")