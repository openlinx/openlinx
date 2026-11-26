"""Verify meta description Rules over Pages in a real crawl store."""

from openlinx.rules.registry import RULES
from openlinx.store.issues import evaluate_rule
from tests.support.crawl_store import crawl_store
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_missing_meta_description(temp_workspace: TempWorkspace) -> None:
    file = crawl_store(
        temp_workspace,
        pages={
            "https://example.com/empty": (
                '<meta name="description" content="">'
                '<meta name="description" content="Second description">'
                '<meta name="robots" content="noindex">'
            ),
            "https://example.com/present": '<meta name="description" content="Buy shoes">',
        },
        completed=False,
    )
    rows = query(
        file,
        "SELECT url_path, url_id, meta_description_count, meta_description_1, "
        "meta_description_2, indexability_status FROM pages ORDER BY url_path",
    )
    measurements = [
        (path, count, first, second, status) for path, _, count, first, second, status in rows
    ]
    assert measurements == [
        ("/", 0, None, None, None),
        ("/empty", 2, "", "Second description", "noindex"),
        ("/present", 1, "Buy shoes", None, None),
    ]
    paths = {url_id: path for path, url_id, *_ in rows}
    matching = [rule for rule in RULES if rule.id == "meta-description-missing"]
    assert len(matching) == 1, "The catalogue must register meta-description-missing once"
    [rule] = matching
    assert (rule.category, rule.issue_type, rule.priority, rule.applies_to, rule.thresholds) == (
        "meta_descriptions",
        "opportunity",
        "medium",
        "internal_pages",
        (),
    )

    affected = [(paths[item.url_id], item.detail) for item in evaluate_rule(file, rule)]
    assert sorted(affected, key=lambda item: item[0]) == [("/", None), ("/empty", None)]
