"""The post-crawl Issues pass: the Rules' stored Affected URLs, then the Health Score over them
(040-add-rules D5, D6, D8)."""

from collections.abc import Sequence

from spider.clock import Clock
from spider.rules.model import Rule
from spider.store.health import health_unit
from spider.store.issue_units import affected_urls_unit, enabled_rule_ids
from spider.store.writer import CrawlWriter


async def materialise_issues(writer: CrawlWriter, catalogue: Sequence[Rule], clock: Clock) -> None:
    """The Rules that the Crawl's rules table marks enabled, then the Health Score over their
    rows."""
    enabled = await writer.run_async(enabled_rule_ids)
    for rule in catalogue:
        if rule.id in enabled:
            await writer.run_async(affected_urls_unit(rule))
    await writer.run_async(health_unit(clock.now()))
