"""Small example utilities used by the test suite."""


def normalize_text(value: str) -> str:
    """Normalize a text value for stable comparisons."""

    return " ".join(value.split()).strip().lower()
