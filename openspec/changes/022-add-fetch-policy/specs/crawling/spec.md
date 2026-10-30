## MODIFIED Requirements

### Requirement: Backstops

**In short:** a run of Internal requests without a response pauses the Crawl and probes the Seed instead of recording the site as errors, and a watchdog cancels a request that hangs.

- **The network pause:** when `max(8, 2 × --concurrency)` requests in a row for Internal URLs end without an HTTP response, the Crawl SHALL pause instead of recording the rest of the site as errors.
  - **Without an HTTP response** means the `fetch_error` `dns_error`, `connection_refused`, `connection_error`, `invalid_response` or `watchdog`, or `022-add-fetch-policy`'s `timeout`. `tls_error` SHALL NOT count: a certificate failure is an answer of sorts, and a site-wide one SHALL NOT wait `--network-wait` and then fail with a misleading `site_unreachable`. A response of any status SHALL reset the count, and requests for External URLs SHALL NOT count.
  - **While paused,** no new request SHALL start. Requests in flight SHALL finish: one that gets a response SHALL be recorded, and one that ends without a response SHALL NOT be recorded, so its URL stays `queued` and is requested again when the Crawl resumes.
  - **Probes:** while paused, the Crawl SHALL request the Seed URL at 5, 10, 20 and 40 seconds after the pause began, then every 60 seconds, through the per-host limits of "Per-host concurrency" and "Rate limit". A probe SHALL NOT be recorded as a URL and SHALL NOT count toward `--max-urls`. A probe that gets a response of any status ends the pause:
    - **A dead section:** when the first probe answers before the second probe is due, or before the wait ends when there is no second probe, the failures were the site's own, and the Crawl SHALL resume and keep their errors. For the rest of the run, the failures of requests to an origin with at least 2 of those URLs, the Seed's origin aside, SHALL NOT count toward the pause, and their URLs SHALL still be requested and recorded as errors.
    - **An outage:** when a probe answers later, the URLs whose requests made up the count SHALL be re-queued and requested again, each at most once in a run, and the Crawl SHALL resume.
  - **Giving up:** a probe SHALL start only before `--network-wait <seconds>` have passed since the pause's start (setting `crawl.network_wait`, default 1800). When no probe has got a response by then, the probes in flight SHALL be cancelled, and the Crawl SHALL end as `failed` with `stop_reason` = `site_unreachable`, and URLs not requested SHALL stay `queued`, so the Crawl can be continued. With `--network-wait 0` no probe starts, so the Crawl fails at once. A negative value SHALL be rejected with exit code 2 and error code `invalid_value`. The Command SHALL print the result, write exactly one error diagnostic, with code `site_unreachable` and a hint that says how long the Crawl waited and names `linx resume`, and exit with code 8.
  - **Visibility:** the Crawl SHALL write a `crawl_paused` event when it pauses and a `crawl_resumed` event when it resumes (see "Progress events"), and one counted `network_paused` warning, with `details.count` (the number of pauses) and `details.total_seconds` (the time spent paused).
  - **A stop:** an interrupt or a stop request SHALL end a pause, and the Crawl SHALL stop as it does otherwise. The URL limit's stop SHALL NOT end a pause: it refuses new URLs only, so the pause goes on within the stop's grace, and a retry it would let through still meets the closed gate (`022-add-fetch-policy`).
- **The watchdog:** a request that has not ended within the watchdog time after it started SHALL be cancelled. The watchdog time SHALL be the longer of 120 seconds and the Fetcher's total request deadline plus 30 seconds, so it never cuts a response that the Fetcher still allows. Its URL SHALL be recorded with `fetch_state` = `error` and `fetch_error` = `watchdog`, and the Crawl SHALL go on. A request ended by the watchdog SHALL count as a request without an HTTP response for the network pause.

#### Scenario: A network wait of zero fails at once
- **WHEN** `/` links to `/down/1` to `/down/20` and then to `/p1`, every `/down/<n>` resets its connection, and `linx crawl {site}/ --concurrency 1 --network-wait 0` runs
- **THEN** stdout holds the result with `"state": "failed"` and `"stop_reason": "site_unreachable"`, and `{site}/p1` has `fetch_state` = `queued`

#### Scenario: Losing the site is reported by one error
- **WHEN** `/` links to `/down/1` to `/down/20`, every `/down/<n>` resets its connection, and `linx crawl {site}/ --concurrency 1 --network-wait 0` runs
- **THEN** the Command exits with code 8, and stderr holds exactly one error line, as its last line, with `code` = `site_unreachable` and a `hint` that contains `linx resume`

#### Scenario: A dead section does not stop the Crawl
- **WHEN** a fake Fetcher gets no response for `{site}/down/1` to `{site}/down/20` and answers every other request, `/` links to them and then to `/p1`, and the Crawl runs with `--concurrency 1` and a fake clock
- **THEN** the Crawl State is `completed`, every `{site}/down/<n>` has `fetch_state` = `error`, `{site}/p1` has `fetch_state` = `fetched`, and the result's `warnings` hold an entry with code `network_paused`

#### Scenario: A dead subdomain pauses the Crawl once
- **WHEN** `/` links to 300 URLs on the subdomain `dead.{host}` and then to `/p1` to `/p20`, a fake Fetcher answers 404 for the robots.txt of `dead.{host}` and gets no response for its other URLs, and none for any request to `{host}` from the one for `/p10` on until 120 seconds of clock time have passed, and the Crawl runs with `--subdomains`, `--concurrency 1` and a fake clock
- **THEN** the events hold exactly two `crawl_resumed` events, the first with `data.outcome` = `dead_section` and the second with `data.outcome` = `outage`, every URL on `dead.{host}` has `fetch_state` = `error`, every `{site}/p<n>` has `fetch_state` = `fetched`, and the Crawl State is `completed`

#### Scenario: An outage pauses and resumes the Crawl
- **WHEN** `/` links to `/p1` to `/p20`, a fake Fetcher gets no response for any request from `/p2` on until 30 seconds of clock time have passed, and the Crawl runs with `--concurrency 1` and a fake clock
- **THEN** the events hold one `crawl_paused` event and then one `crawl_resumed` event with `data.outcome` = `outage`, and the Crawl State is `completed`

#### Scenario: URLs that failed in an outage are requested again
- **WHEN** `/` links to `/p1` to `/p20`, a fake Fetcher gets no response for any request from `/p2` on until 30 seconds of clock time have passed, and the Crawl runs with `--concurrency 1` and a fake clock
- **THEN** every `{site}/p<n>` has `fetch_state` = `fetched`

#### Scenario: A Crawl that waits longer than the network wait fails
- **WHEN** `/` links to `/p1` to `/p20`, a fake Fetcher gets no response for any request after the one for `/`, and the Crawl runs with `--concurrency 1`, `--network-wait 30` and a fake clock
- **THEN** the Seed is probed 3 times, and the Crawl ends as `failed` with `stop_reason` = `site_unreachable`

#### Scenario: Probes back off to once a minute
- **WHEN** the probe times of a network wait of 200 seconds are computed
- **THEN** they are 5, 10, 20, 40, 100 and 160 seconds after the pause began

#### Scenario: Progress events say when the Crawl is paused
- **WHEN** a Crawl is paused for 30 seconds of fake-clock time
- **THEN** every `progress` event written during the pause has `data.paused` = true, and every other one `data.paused` = false

#### Scenario: A negative network wait is rejected
- **WHEN** `linx crawl {site}/ --network-wait -1` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_value`

#### Scenario: Dead External links do not fail the Crawl
- **WHEN** `http://site.test/` links to `http://nowhere.test/1` to `http://nowhere.test/12`, which do not resolve, and `linx crawl http://site.test/ --concurrency 1` runs
- **THEN** the Crawl ends with the Crawl State `completed`

#### Scenario: A stuck request is ended by the watchdog
- **WHEN** a fake Fetcher never answers for `{site}/stuck`, `/` links to `/stuck` and `/ok`, and the Crawl runs with the default settings and a fake clock that passes 120 seconds
- **THEN** `{site}/stuck` has `fetch_state` = `error` and `fetch_error` = `watchdog`, and the Crawl State is `completed`

#### Scenario: The URL limit's stop does not end a network pause
- **WHEN** `http://site.test/` links in turn to 30 URLs on each of `site.test`, `blog.site.test` and `shop.site.test`, a fake Fetcher answers the first URL of `site.test` at once and gets no response for the others within 2 seconds, and the Crawl runs with `--scope subdomains`, `--concurrency 4`, `--max-urls 13`, `--timeout 2` and a fake clock
- **THEN** the Crawl stops with `stop_reason` = `max_urls`, a `crawl_paused` event is written after the URL limit's stop, and every URL with `fetch_state` = `error` has `attempt_count` = 1
