"""Text of the HTML, as one model for every column (030-add-page-data D7)."""

import re

# ASCII whitespace only, as document.title has it: a no-break space is text.
_ASCII_WHITESPACE = "\t\n\x0c\r "
_WHITESPACE_RUN = re.compile(r"[\t\n\x0c\r ]+")


def normalized(text: str) -> str:
    return _WHITESPACE_RUN.sub(" ", text).strip(_ASCII_WHITESPACE)
