from decimal import Decimal

import pytest

from srm_tracker.attendance.parser import AttendanceParseError, parse_attendance_html


def test_parses_documented_course_table(valid_html: str) -> None:
    records = parse_attendance_html(valid_html)

    assert len(records) == 2
    assert records[0].code == "21CSE385J"
    assert records[0].subject == "ADVANCED MALWARE ANALYSIS"
    assert records[0].total_hours == 23
    assert records[0].attended_hours == 16
    assert records[0].absent_hours == 7
    assert records[0].source_percentage == Decimal("69.57")
    assert records[1].source_percentage == Decimal("100")


def test_rejects_login_page(login_html: str) -> None:
    with pytest.raises(AttendanceParseError, match="authentication"):
        parse_attendance_html(login_html)


def test_rejects_invalid_integer_and_does_not_return_partial_records(malformed_html: str) -> None:
    with pytest.raises(AttendanceParseError, match="whole number"):
        parse_attendance_html(malformed_html)


def test_rejects_row_with_inconsistent_totals(valid_html: str) -> None:
    invalid_html = valid_html.replace("<td>7</td>", "<td>6</td>", 1)

    with pytest.raises(AttendanceParseError, match="do not add up"):
        parse_attendance_html(invalid_html)


def test_rejects_response_without_attendance_table() -> None:
    with pytest.raises(AttendanceParseError, match="Attendance table"):
        parse_attendance_html("<html><body><table><tr><td>No data</td></tr></table></body></html>")
