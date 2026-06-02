from pydantic import BaseModel
from typing import Optional

class LineItem(BaseModel):
    description: str
    quantity: Optional[int] = None        # sometimes not explicit
    unit_price: Optional[float] = None    # sometimes not explicit
    amount: float

class Invoice(BaseModel):
    # Loosened required fields — not every invoice has these
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    sender_company: str
    receiver_company: str
    line_items: list[LineItem]
    subtotal: Optional[float] = None
    total_amount: float

    # Optional fields
    gstin_sender: Optional[str] = None
    gstin_receiver: Optional[str] = None
    gst: Optional[float] = None  # when GST isn't broken into CGST/SGST/IGST
    cgst: Optional[float] = None
    sgst: Optional[float] = None
    igst: Optional[float] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    due_date: Optional[str] = None