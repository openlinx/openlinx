"""Text of the HTML, as one model for every column (030-add-page-data D7)."""

import re

# ASCII whitespace only, as document.title has it: a no-break space is text.
_ASCII_WHITESPACE = "\t\n\x0c\r "
_WHITESPACE_RUN = re.compile(f"[{_ASCII_WHITESPACE}]+")


def normalized(text: str) -> str:
    return trimmed(_WHITESPACE_RUN.sub(" ", text))


def trimmed(text: str) -> str:
    return text.strip(_ASCII_WHITESPACE)
