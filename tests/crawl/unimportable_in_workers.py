"""An extractor whose module a parse worker cannot import (026 design D1).

A spawn child names itself before it unpickles its start arguments, which import this module.
"""

import multiprocessing

import msgspec
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.pages import Extractor, PageInput

if multiprocessing.current_process().name != "MainProcess":
    raise ImportError("a parse worker cannot import this module")


class Nothing(msgspec.Struct, frozen=True):
    pass


def _nothing(tree: LexborHTMLParser, page: PageInput) -> Nothing:
    return Nothing()


UNIMPORTABLE_IN_WORKERS = Extractor("unimportable_in_workers", _nothing)
