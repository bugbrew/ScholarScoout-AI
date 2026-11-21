from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class UserProfile:
    qualification: str                  # e.g., "B.Tech Computer Science", "12th Pass", "MBA"
    education_level: str                # "High School / 12th" | "Undergraduate (B.Tech/B.Sc/B.A)" | "Postgraduate (M.Tech/M.Sc/MBA)" | "PhD"
    current_stage: str                  # e.g., "1st Year" .. "4th Year", "Final Year", "Graduate"
    graduation_year: Optional[int] = None
    skills: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    location: Optional[str] = None
    strict_eligibility: bool = True


@dataclass
class Opportunity:
    title: str
    category: str                       # "scholarship" | "internship" | "course" | "job"
    organization: str
    url: str
    summary: str
    eligibility_tags: List[str] = field(default_factory=list)
    source_name: str = "web"
    match_score: float = 0.0
    eligibility_note: str = "Matches general profile"


@dataclass
class ResearchResource:
    title: str
    url: str
    snippet: str
    source_name: str
    published_info: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[str] = None
    venue_or_id: Optional[str] = None