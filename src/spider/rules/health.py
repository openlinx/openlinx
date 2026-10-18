"""The Health Score's formula (040-add-rules D8)."""


def health_score(internal_pages: int, affected_pages: int) -> int:
    # Rounded down, so 100 means that no Page has an Issue-type Issue.
    return 100 * (internal_pages - affected_pages) // internal_pages
