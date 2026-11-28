# Pre-Health Rules preview Crawl files

`preview-wal.sqlite.gz` and `preview-delete.sqlite.gz` are compressed SQLite files from
`18fa7640d3a2a9754d0f55af3b97bd4f2399a0ad`. In a temporary Workspace, run that
producer's `linx init`, set `[store] journal_mode` to `wal` or `delete` and
`[rules.title-too-long] max_chars = 70`, then run
`linx crawl http://127.0.0.1:<port> --max-urls 1 --concurrency 1`.
The root HTML is `<title>Index</title><a href="/guide?p=1">Guide</a>`.
Compress the stopped Crawl after the CLI closes the file and checkpoints WAL.

The tests decompress fresh copies and update only the loopback port in `seeds.url`
and `urls.url` for their local fixture server. The DDL and both Rule snapshots
come from the producer, including the three exact placeholder queries.
