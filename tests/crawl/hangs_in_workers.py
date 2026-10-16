"""An extractor whose module never finishes importing in a parse worker (026 design D8).

A spawn child names itself before it unpickles its snapshot, which imports this module.
"""

import multiprocessing
import time

import msgspec
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.pages import Extractor, PageInput

if multiprocessing.current_process().name != "MainProcess":
    time.sleep(120)


class Nothing(msgspec.Struct, frozen=True):
    pass


def _nothing(tree: LexborHTMLParser, page: PageInput) -> Nothing:
    return Nothing()


HANGS_IN_WORKERS = Extractor("hangs_in_workers", _nothing)
