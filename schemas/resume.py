from pydantic import BaseModel
from typing import Optional

class WorkExperience(BaseModel):
    company_name: Optional[str] = None
    role: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None

class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    year: Optional[str] = None

class Resume(BaseModel):
    # Personal Info
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None  # str not int — handles +91, leading zeros
    address: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None

    # Skills — list of strings, not a separate class
    technical_skills: list[str] = []
    soft_skills: list[str] = []
    tech_stack: list[str] = []

    # Experience & Education
    work_experience: list[WorkExperience] = []
    education: list[Education] = []

    # Projects
    projects: list[str] = []

    # Summary
    summary: Optional[str] = None