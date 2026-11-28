# Crawl control

## Crawl State

A new Crawl starts as `running`. Its process records `completed` when it reaches the end,
`stopped` on a graceful stop, or `failed` if it cannot continue. A `completed` Crawl is final.
The [Crawl Service can continue](crawling.md#continuing-a-crawl) a `stopped` or `failed` Crawl,
which puts it back into `running` and clears its stop reason. A process that dies before it
records an end leaves the file `running`. Detecting these Crawls as `interrupted` and
continuing them with `linx resume` are planned separately.

## Read Crawl status

Run `linx status` for the latest Crawl, or use `linx status --crawl <ref>` with a Crawl ID
or a crawl file path. This reads the selected Store without writing to it.

For a completed Crawl, `completed_at` gives the recorded completion time and `eta_s` is null.
`urls` gives the exact discovered, fetched, error, skipped and queued counts.
`status_classes` groups recorded HTTP responses by class, so a fetched 404 contributes
to `fetched` and `4xx`. While a Crawl is running, `urls`, `status_classes` and `eta_s`
are null.

## Stop a foreground Crawl

From another terminal in the Workspace, run:

```sh
linx stop --crawl 20261128-120000-a1b2
```

Use the Crawl ID printed by `linx crawl`. With no `--crawl` option, Stop selects `latest`.
The Command records a stop request in the crawl file. The Crawl starts no new requests,
gives requests in flight up to 10 seconds, stores their completed results and runs the
post-crawl passes. Unfinished URLs stay `queued`. If the Crawl is waiting for the network,
it ends the pause without waiting for the next Seed probe. An interrupt or failure that
already determined the outcome retains its stop reason.

After the request commits, Stop waits up to 60 seconds by default. Set `--wait <seconds>`
to choose the wait or `--wait 0` to return after recording the request. The Command prints
`crawl_id`, `state`, `stop_reason` and `stop_requested` and exits with code 0 on success.

- When it observes a completed stop, the result has `state: stopped`, `stop_reason: requested`
  and `stop_requested: false`. The Crawl prints its own result and exits with code 0.
- With `--wait 0` or when the deadline expires while Stop is still waiting, the reply has
  `state: running`, `stop_reason: null` and `stop_requested: true`. The recorded request
  remains in the crawl file for the owner to act on.
- If the Crawl has already ended when Stop is ready to record the request, the Command
  reports its state and leaves the crawl file unchanged. Repeating Stop on a `completed`
  Crawl gives the same result.

The [crawl file](crawl-store.md) records which run handled a request and when.
