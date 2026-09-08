from decimal import Decimal

import pytest

from srm_tracker.attendance.calculations import (
    AttendanceCalculationError,
    calculate_attendance_guidance,
)


def test_returns_no_guidance_when_no_hours_have_been_reported() -> None:
    result = calculate_attendance_guidance(0, 0, Decimal("75"))

    assert result.current_percentage is None
    assert result.additional_attended_hours is None
    assert result.additional_absences_allowed is None
    assert result.target_reachable is False


def test_calculates_guidance_when_exactly_on_target() -> None:
    result = calculate_attendance_guidance(15, 20, Decimal("75"))

    assert result.current_percentage == Decimal("75")
    assert result.additional_attended_hours == 0
    assert result.additional_absences_allowed == 0
    assert result.target_reachable is True


def test_calculates_hours_needed_below_target() -> None:
    result = calculate_attendance_guidance(16, 23, Decimal("75"))

    assert result.additional_attended_hours == 5
    assert result.additional_absences_allowed == 0
    assert result.target_reachable is True


def test_rounds_current_percentage_to_two_decimal_places() -> None:
    result = calculate_attendance_guidance(16, 23, Decimal("75"))

    assert result.current_percentage == Decimal("69.57")


def test_calculates_absences_allowed_above_target() -> None:
    result = calculate_attendance_guidance(18, 20, Decimal("75"))

    assert result.current_percentage == Decimal("90")
    assert result.additional_attended_hours == 0
    assert result.additional_absences_allowed == 4
    assert result.target_reachable is True


def test_marks_imperfect_attendance_as_unreachable_at_one_hundred_percent() -> None:
    result = calculate_attendance_guidance(16, 23, Decimal("100"))

    assert result.additional_attended_hours is None
    assert result.additional_absences_allowed == 0
    assert result.target_reachable is False


def test_keeps_perfect_attendance_at_one_hundred_percent() -> None:
    result = calculate_attendance_guidance(20, 20, Decimal("100"))

    assert result.additional_attended_hours == 0
    assert result.additional_absences_allowed == 0
    assert result.target_reachable is True


@pytest.mark.parametrize("target", [Decimal("0"), Decimal("-5"), Decimal("100.01")])
def test_rejects_target_outside_one_to_one_hundred(target: Decimal) -> None:
    with pytest.raises(AttendanceCalculationError, match="between 0 and 100"):
        calculate_attendance_guidance(16, 23, target)
