"""Target-attendance guidance based on cumulative subject totals."""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal


class AttendanceCalculationError(ValueError):
    """Raised when attendance totals or a target cannot be calculated safely."""


@dataclass(frozen=True, slots=True)
class AttendanceGuidance:
    """Current attendance and actionable guidance for one target percentage."""

    current_percentage: Decimal | None
    additional_attended_hours: int | None
    additional_absences_allowed: int | None
    target_reachable: bool


def calculate_attendance_guidance(
    attended_hours: int,
    total_hours: int,
    target_percentage: Decimal,
) -> AttendanceGuidance:
    """Calculate future attendance and absence limits without rounding source totals."""
    _validate_inputs(attended_hours, total_hours, target_percentage)
    if total_hours == 0:
        return AttendanceGuidance(None, None, None, False)

    current_percentage = (Decimal(attended_hours) * Decimal("100") / Decimal(total_hours)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    target_ratio = target_percentage / Decimal("100")
    if target_percentage == Decimal("100"):
        return _one_hundred_percent_guidance(attended_hours, total_hours, current_percentage)

    additional_attended = _additional_attended_hours(
        attended_hours,
        total_hours,
        target_ratio,
    )
    additional_absences = _additional_absences_allowed(
        attended_hours,
        total_hours,
        target_ratio,
    )
    return AttendanceGuidance(
        current_percentage=current_percentage,
        additional_attended_hours=additional_attended,
        additional_absences_allowed=additional_absences,
        target_reachable=True,
    )


def _validate_inputs(
    attended_hours: int,
    total_hours: int,
    target_percentage: Decimal,
) -> None:
    if attended_hours < 0 or total_hours < 0 or attended_hours > total_hours:
        raise AttendanceCalculationError(
            "attendance hours must be non-negative and internally consistent"
        )
    if not target_percentage.is_finite() or not Decimal("0") < target_percentage <= Decimal("100"):
        raise AttendanceCalculationError("target percentage must be between 0 and 100")


def _one_hundred_percent_guidance(
    attended_hours: int,
    total_hours: int,
    current_percentage: Decimal,
) -> AttendanceGuidance:
    if attended_hours == total_hours:
        return AttendanceGuidance(current_percentage, 0, 0, True)
    return AttendanceGuidance(current_percentage, None, 0, False)


def _additional_attended_hours(attended_hours: int, total_hours: int, target_ratio: Decimal) -> int:
    required = (target_ratio * Decimal(total_hours) - Decimal(attended_hours)) / (
        Decimal("1") - target_ratio
    )
    return max(0, int(required.to_integral_value(rounding=ROUND_CEILING)))


def _additional_absences_allowed(
    attended_hours: int,
    total_hours: int,
    target_ratio: Decimal,
) -> int:
    allowed = Decimal(attended_hours) / target_ratio - Decimal(total_hours)
    return max(0, int(allowed.to_integral_value(rounding=ROUND_FLOOR)))
