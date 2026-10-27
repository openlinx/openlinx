"""The units of the post-crawl Issues pass that store the Rules' Affected URLs (040-add-rules
D5)."""

from collections.abc import Callable

from sqlalchemy import Connection, bindparam, delete, insert, literal, select

from spider.store.issues import ENABLED_RULES, rule_query
from spider.store.rule_queries import RuleQuery
from spider.store.schema import affected_urls

_DELETE = delete(affected_urls).where(affected_urls.c.rule_id == bindparam("rule_id"))


def affected_urls_unit(rule: RuleQuery) -> Callable[[Connection], None]:
    """A unit that replaces the Rule's rows in affected_urls with those its query returns."""
    found = rule_query(rule)
    statement = insert(affected_urls).from_select(
        ["rule_id", "url_id", "detail"], select(literal(rule.id), found.c.url_id, found.c.detail)
    )

    def unit(connection: Connection) -> None:
        connection.execute(_DELETE, {"rule_id": rule.id})
        connection.execute(statement)

    return unit


def enabled_rule_ids(connection: Connection) -> frozenset[str]:
    """The Rules that the Crawl's rules table marks enabled."""
    return frozenset(row.id for row in connection.execute(ENABLED_RULES))
