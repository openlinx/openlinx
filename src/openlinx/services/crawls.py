"""Creating a Crawl, which the Crawl service builds on (design D9 of 015-add-crawl-store)."""

import secrets
from dataclasses import replace

from openlinx.clock import Clock
from openlinx.output.reporter import Reporter
from openlinx.store.ids import Choice
from openlinx.store.records import CrawlFile, NewCrawl


def create_crawl(
    request: NewCrawl, clock: Clock, reporter: Reporter, choice: Choice = secrets.choice
) -> CrawlFile:
    # Imported here: sqlalchemy stays off the CLI's startup path (design D9).
    from openlinx.store.crawls import create_crawl_file
    from openlinx.store.journal import choose_journal_mode
    from openlinx.store.redaction import redact

    # Before anything is written: no part of the crawl file may hold a secret (design D7).
    redacted = redact(request.command_argv, request.config, request.secret_names)
    request = replace(request, command_argv=redacted.command_argv, config=redacted.config)
    journal = choose_journal_mode(request.journal_setting, request.workspace.data_dir)
    # Read once: the id and crawl.started_at must name the same instant.
    crawl_file, journal = create_crawl_file(request, clock.now(), choice, journal)
    if journal.warning is not None:
        reporter.warn(journal.warning)
    return crawl_file
