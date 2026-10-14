"""The robots directives parser (020-add-crawl-core D6; seam 4)."""

from selectolax.lexbor import LexborHTMLParser

from spider.crawl.directives import RobotsDirectives, meta_robots_contents, robots_directives


def test_meta_robots_directives_are_read_case_insensitively() -> None:
    tree = LexborHTMLParser('<meta name="ROBOTS" content="NOINDEX, follow">')

    directives = robots_directives(meta_robots_contents(tree), (), "spider")

    assert (
        directives.meta_robots,
        directives.meta_robots_noindex,
        directives.meta_robots_nofollow,
    ) == ("NOINDEX, follow", True, False)


def test_no_directives_give_nulls_and_no_verdicts() -> None:
    assert robots_directives((), (), "spider") == RobotsDirectives(
        meta_robots=None,
        meta_robots_noindex=False,
        meta_robots_nofollow=False,
        x_robots_tag=None,
        x_robots_tag_noindex=False,
        x_robots_tag_nofollow=False,
    )


def test_a_header_for_another_crawler_does_not_apply() -> None:
    directives = robots_directives((), ("googlebot: noindex",), "spider")

    assert (directives.x_robots_tag, directives.x_robots_tag_noindex) == (
        "googlebot: noindex",
        False,
    )
