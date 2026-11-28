"""Coordinate the Crawl frontier, URL recording and extension hooks.

dispatch: run_crawl. context: CrawlContext. hooks: Hooks, Handler, handler, Pass, PassContext,
PassWriter, UrlResult, UrlResponse. stop: StopSignal. warning_log: WarningLog.
pause: pause_after. outcomes: RecordingFailedError. blocking: BlockingRuns, BLOCKING_RUN.
heartbeat: watch_stop_requests.
"""
