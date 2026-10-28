"""The Content Area and its counts (030-add-page-data, page-data; seam 4)."""

from spider.extract.content import ContentArea
from tests.support.page_data import page_row

# The spec's fixture A, which later scenarios refer to.
FIXTURE_A = """<html lang="en"><head><title>Hello</title></head><body>
<header><p>Site header text</p></header>
<nav><a href="/">Home</a></nav>
<main><h1>Welcome</h1><p>Reading is fun. Water is wet.</p></main>
<footer><p>Footer text</p></footer>
</body></html>"""


def test_default_content_area_leaves_out_navigation() -> None:
    assert page_row(FIXTURE_A).word_count == 7


def test_empty_exclude_list_counts_everything() -> None:
    assert page_row(FIXTURE_A, content_area=ContentArea(exclude=())).word_count == 13
