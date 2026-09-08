"""Typed values produced by the portal parser."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AttendanceRecord:
    """One course-wise cumulative attendance total reported by SRM."""

    code: str
    subject: str
    total_hours: int
    attended_hours: int
    absent_hours: int
    source_percentage: Decimal
