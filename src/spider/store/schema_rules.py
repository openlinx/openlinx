"""The Rule tables and views of the declared public schema, which spider.store.schema re-exports
into its one metadata (040-add-rules D14, D19). Import them from spider.store.schema."""

from typing import Any

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    Select,
    Table,
    Text,
    func,
    or_,
    select,
)

from spider.naming import APP_NAME, SETTINGS_FILE_NAME
from spider.store.records import AppliesTo, IssueType, Priority, RuleCategory
from spider.store.schema import (
    literal_values,
    pages,
    public_table,
    public_view,
    urls,
)
from spider.store.types import Flag, Json

rules: Table = public_table(
    "rules",
    Column(
        "id",
        Text,
        primary_key=True,
        comment=f"The Rule id, as typed in {APP_NAME} rules show and {SETTINGS_FILE_NAME}.",
    ),
    Column(
        "category",
        Text,
        nullable=False,
        comment="The Rule's category.",
        info={"values": literal_values(RuleCategory)},
    ),
    Column(
        "issue_type",
        Text,
        nullable=False,
        comment="The Issue Type of the Rule's Issues.",
        info={"values": literal_values(IssueType)},
    ),
    Column(
        "priority",
        Text,
        nullable=False,
        comment="The Priority of the Rule's Issues.",
        info={"values": literal_values(Priority)},
    ),
    Column(
        "applies_to",
        Text,
        nullable=False,
        comment="The population the Rule is evaluated over.",
        info={"values": literal_values(AppliesTo)},
    ),
    Column("enabled", Flag, nullable=False, comment="1 when the Rule was evaluated in this Crawl."),
    Column(
        "thresholds",
        Json,
        nullable=False,
        comment="The effective thresholds, as an object of names to integers; {} for a Rule "
        "without thresholds.",
    ),
    Column("description", Text, nullable=False, comment="What the Rule checks."),
    Column("why_it_matters", Text, nullable=False, comment="Why its Issues matter."),
    Column("how_to_fix", Text, nullable=False, comment="How to fix its Issues."),
    Column(
        "reproduce_sql",
        Text,
        nullable=False,
        comment="The Rule's reproducing query: a read-only SELECT over this file that returns its "
        "Affected URLs as url_id and detail.",
    ),
    comment="One row for each Rule of the catalogue, with the configuration the Crawl was "
    "created with, which it uses throughout.",
    change=40,
)

affected_urls: Table = public_table(
    "affected_urls",
    Column(
        "rule_id",
        Text,
        ForeignKey("rules.id"),
        primary_key=True,
        comment="The Rule that fired.",
    ),
    Column(
        "url_id",
        Integer,
        ForeignKey("urls.id"),
        primary_key=True,
        autoincrement=False,
        comment="The Affected URL.",
    ),
    Column(
        "detail",
        Json,
        comment="The measured values, as an object with the keys listed for the Rule; NULL "
        "when the Rule lists none.",
    ),
    comment="One row for each Rule and its Affected URL, written only by the post-crawl pass: "
    "the result of the last pass.",
    change=40,
    without_rowid=True,
)
Index(
    "affected_urls_url_id",
    affected_urls.c.url_id,
    info={"description": "The Issues of one URL, and the Health Score's count of affected Pages."},
)

issues: Table = public_view(
    "issues",
    Column(
        "rule_id",
        Text,
        nullable=False,
        comment="The Rule that fired.",
        info={"references": "rules.id"},
    ),
    Column(
        "category",
        Text,
        nullable=False,
        comment="The Rule's category.",
        info={"values": literal_values(RuleCategory)},
    ),
    Column(
        "issue_type",
        Text,
        nullable=False,
        comment="The Issue Type of the Rule's Issues.",
        info={"values": literal_values(IssueType)},
    ),
    Column(
        "priority",
        Text,
        nullable=False,
        comment="The Priority of the Rule's Issues.",
        info={"values": literal_values(Priority)},
    ),
    Column(
        "affected_count",
        Integer,
        nullable=False,
        comment="The number of the Rule's rows in affected_urls.",
    ),
    # Grouped by the primary key's prefix, so the count reads affected_urls in key order.
    query=select(
        rules.c.id.label("rule_id"),
        rules.c.category,
        rules.c.issue_type,
        rules.c.priority,
        func.count().label("affected_count"),
    )
    .join_from(affected_urls, rules, affected_urls.c.rule_id == rules.c.id)
    .group_by(affected_urls.c.rule_id),
    comment="The Issues: one row for each Rule with at least one Affected URL, counted from "
    "affected_urls, so it holds the result of the last post-crawl pass.",
    change=40,
)


def _population(name: str, query: Select[Any], comment: str) -> Table:
    """The URL ids of a population, which a Rule's query joins (040-add-rules D19)."""
    return public_view(
        name,
        Column(
            "url_id",
            Integer,
            nullable=False,
            comment="A member of the population.",
            info={"references": "urls.id"},
        ),
        query=query,
        comment=comment,
        change=40,
    )


def _analysed_page_ids() -> Select[Any]:
    return (
        select(pages.c.url_id)
        .join_from(pages, urls, pages.c.url_id == urls.c.id)
        .where(urls.c.parsed == 1)
    )


internal_urls: Table = _population(
    "internal_urls",
    select(urls.c.id.label("url_id")).where(
        urls.c.is_internal == 1,
        or_(urls.c.fetch_state.in_(("fetched", "error")), urls.c.blocked_by_robots_txt == 1),
    ),
    "The Internal URLs that were requested, or that robots.txt disallows.",
)
analysed_pages: Table = _population(
    "analysed_pages",
    _analysed_page_ids(),
    "The Pages that were parsed, also when one of their extractors failed.",
)
indexable_pages: Table = _population(
    "indexable_pages",
    _analysed_page_ids(),
    "The analysed Pages that are indexable. The store records no Indexability yet, so it holds "
    "every analysed Page.",
)
