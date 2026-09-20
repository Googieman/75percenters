"""Strict parsing for the authenticated SRM course-wise attendance table."""

from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup
from bs4.element import Tag

from srm_tracker.attendance.models import AttendanceRecord

EXPECTED_HEADERS = (
    "code",
    "description",
    "max. hours",
    "attended hours",
    "absent hours",
    "total percentage",
)
HEADER_VARIANTS = (
    {"code"},
    {"description"},
    {"max. hours"},
    {"attended hours", "att. hours"},
    {"absent hours"},
    {"total percentage"},
)


class AttendanceParseError(ValueError):
    """Raised when an SRM response cannot be safely treated as attendance data."""


def parse_attendance_html(html: str) -> list[AttendanceRecord]:
    """Parse the documented attendance table or raise instead of returning unsafe data."""
    soup = BeautifulSoup(html, "html.parser")
    if _looks_like_authentication_page(soup):
        raise AttendanceParseError("authentication page detected; log into SRM normally and retry")

    table, header_row_index = _find_attendance_table(soup)
    records: list[AttendanceRecord] = []
    for row in table.find_all("tr")[header_row_index + 1 :]:
        cells = row.find_all("td", recursive=False)
        if not cells:
            continue
        if len(cells) != len(EXPECTED_HEADERS):
            raise AttendanceParseError("attendance row has an unexpected number of cells")
        records.append(_parse_record([_cell_text(cell) for cell in cells]))

    if not records:
        raise AttendanceParseError("attendance table contains no usable records")
    return records


def _looks_like_authentication_page(soup: BeautifulSoup) -> bool:
    title = _normalized_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    has_password_input = soup.select_one("form input[type='password']") is not None
    return "login" in title or has_password_input


def _find_attendance_table(soup: BeautifulSoup) -> tuple[Tag, int]:
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for index, row in enumerate(rows):
            headers = row.find_all(["th", "td"], recursive=False)
            normalized_headers = tuple(_normalized_text(_cell_text(header)) for header in headers)
            if len(normalized_headers) == len(HEADER_VARIANTS) and all(
                header in variants
                for header, variants in zip(normalized_headers, HEADER_VARIANTS, strict=True)
            ):
                return table, index
    raise AttendanceParseError("Attendance table not found in SRM response")


def _parse_record(cells: list[str]) -> AttendanceRecord:
    code, subject, total, attended, absent, percentage = cells
    if not code or not subject:
        raise AttendanceParseError("attendance row is missing a course code or subject")

    total_hours = _parse_non_negative_integer(total, "Max. hours")
    attended_hours = _parse_non_negative_integer(attended, "Attended hours")
    absent_hours = _parse_non_negative_integer(absent, "Absent hours")
    if attended_hours + absent_hours != total_hours:
        raise AttendanceParseError("attendance row totals do not add up")

    source_percentage = _parse_percentage(percentage)
    return AttendanceRecord(
        code=code,
        subject=subject,
        total_hours=total_hours,
        attended_hours=attended_hours,
        absent_hours=absent_hours,
        source_percentage=source_percentage,
    )


def _parse_non_negative_integer(value: str, label: str) -> int:
    if not value.isascii() or not value.isdigit():
        raise AttendanceParseError(f"{label} must be a non-negative whole number")
    return int(value)


def _parse_percentage(value: str) -> Decimal:
    normalized = value.removesuffix("%").strip()
    try:
        percentage = Decimal(normalized)
    except InvalidOperation as error:
        raise AttendanceParseError("Total Percentage must be numeric") from error
    if not percentage.is_finite() or not Decimal("0") <= percentage <= Decimal("100"):
        raise AttendanceParseError("Total Percentage must be between 0 and 100")
    return percentage


def _cell_text(cell: Tag) -> str:
    return cell.get_text(" ", strip=True)


def _normalized_text(value: str) -> str:
    return " ".join(value.split()).casefold()
