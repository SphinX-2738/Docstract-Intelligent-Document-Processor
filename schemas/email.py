from pydantic import BaseModel
from typing import Optional

class Email(BaseModel):
    sender_name: str
    receiver_name: str
    subject: str
    date: Optional[str] = None      # not always present
    body: Optional[str] = None      # sometimes LLM skips this
    key_points: list[str] = []
    action_items: list[str] = []
    sender_email: Optional[str] = None
    receiver_email: Optional[str] = None
    tone: Optional[str] = None
    priority: Optional[str] = None