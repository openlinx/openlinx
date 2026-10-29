## ADDED Requirements

### Requirement: A hook failure names its error

**In short:** the first counted `handler_failed` and `parse_failed` warnings say what the error was and where it was raised.

The warning that "One URL never stops the Crawl" writes for the first URL a handler or an extractor failed on SHALL hold, besides `count` and `first_url`:
- `details.error`: the error's text, at most 300 characters;
- `details.at`: `<file>:<line>` of the frame that raised it, the file relative to the package or project it belongs to.

`parse_error_message` SHALL stay as "One URL never stops the Crawl" says: the extractor's name and the error's type.

#### Scenario: A failing handler names its error
- **WHEN** a handler registered for the test raises `KeyError("title")` on `{site}/boom`, `/` links to `/boom`, and `linx crawl {site}/` ends
- **THEN** the result's `handler_failed` warning has `details.error` = `'title'`, and a `details.at` that names the handler's file and line

#### Scenario: A failing extractor names its error
- **WHEN** an extractor registered for the test raises `ValueError("no body")` on `{site}/boom`, `/` links to `/boom`, and `linx crawl {site}/` ends
- **THEN** the result's `parse_failed` warning has `details.error` = `no body` and a `details.at` that names the extractor's file and line, and `{site}/boom` has the `parse_error_message` `<name>: ValueError`
