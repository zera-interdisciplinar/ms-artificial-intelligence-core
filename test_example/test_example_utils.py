"""Example unit tests for contributors."""

import pytest

from test_example.example_utils import normalize_text


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("  Hello   World ", "hello world"),
        ("FASTAPI\n\n  CI", "fastapi ci"),
        ("   Mixed Case   Text   ", "mixed case text"),
    ],
)
def test_normalize_text(raw_value: str, expected: str) -> None:
    """Arrange, act, and assert the normalization behavior."""

    result = normalize_text(raw_value)

    assert result == expected
