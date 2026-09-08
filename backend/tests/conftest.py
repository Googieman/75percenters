"""Shared backend test configuration."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_html() -> str:
    return (FIXTURES_DIR / "attendance-valid.html").read_text(encoding="utf-8")


@pytest.fixture
def login_html() -> str:
    return (FIXTURES_DIR / "attendance-login.html").read_text(encoding="utf-8")


@pytest.fixture
def malformed_html() -> str:
    return (FIXTURES_DIR / "attendance-malformed.html").read_text(encoding="utf-8")
