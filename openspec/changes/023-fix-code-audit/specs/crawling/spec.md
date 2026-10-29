## ADDED Requirements

### Requirement: A hook failure names its error

**In short:** the first counted `handler_failed` and `parse_failed` warnings say what the error was and where in the hook it was raised.

The warning that "One URL never stops the Crawl" writes for the first URL a handler or an extractor raised on SHALL hold, besides `count` and `first_url`:
- `details.error`: the error's text, at most 300 characters;
- `details.at`: `<file>:<line>`, where the line is that of the deepest frame of the traceback in the file that defines the hook's function, and the file is that file's path relative to the folder that holds its top-level package, with `/` between its parts on every OS, such as `tests/crawl/test_hooks.py:88`.

A `parse_failed` warning whose first URL raised nothing, a page preparation that gave nothing (`body_too_large`, `worker_crashed`, `parse_timeout`), SHALL have neither key.

#### Scenario: A failing handler names its error
- **WHEN** a handler registered for the test, defined in `tests/crawl/test_hooks.py`, raises `KeyError("title")` on `{site}/boom`, `/` links to `/boom`, and `linx crawl {site}/` ends
- **THEN** the result's `handler_failed` warning has `details.error` = `'title'`, and `details.at` = `tests/crawl/test_hooks.py:<n>`, where n is the line of the `raise`

#### Scenario: A failing extractor names its error
- **WHEN** an extractor registered for the test, defined in `tests/crawl/test_hooks.py`, raises `ValueError("no body")` on `{site}/boom`, `/` links to `/boom`, and `linx crawl {site}/` ends
- **THEN** the result's `parse_failed` warning has `details.error` = `no body` and `details.at` = `tests/crawl/test_hooks.py:<n>`, where n is the line of the `raise`, and `{site}/boom` has the `parse_error_message` `<name>: ValueError`

#### Scenario: A preparation that gave nothing names no error
- **WHEN** a page executor registered for the test gives `{site}/boom` the `parse_error` `worker_crashed`, `/` links to `/boom`, and `linx crawl {site}/` ends
- **THEN** the result's `parse_failed` warning has no `details.error` and no `details.at`
