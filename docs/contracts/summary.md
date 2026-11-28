# Crawl summary JSON contract

`linx summary` returns one JSON object for the selected Crawl. All values come
from one snapshot of the Crawl store. A running Crawl includes the rows committed
when the read begins. Use `linx status` to poll progress from the recorded heartbeat
counters. The HTML Report uses this same summary model.

## Members

| Member | Type and meaning |
|---|---|
| `summary_version` | Integer, currently `1`. Adding members keeps the version. Removing or renaming a member, or changing its meaning, increases the version. |
| `crawl` | Object. `id`, `tool_version` and `started_at` are strings. `completed_at` is a string in the completed state, otherwise null. Timestamps are ISO 8601 in UTC. `schema_version` and `seed_count` are integers. `seeds` lists up to the first ten recorded Seed URL strings in their recorded order. `crawl_mode` is `spider`, `list` or `sitemap`. `state` is `running`, `stopped`, `completed`, `failed` or `interrupted`. `stop_reason` is the recorded reason for a stopped or failed Crawl, otherwise null. `section_crawl` is a boolean. `link_metrics` is `partial` for a Section Crawl and `complete` for a whole-site Crawl. |
| `segment` | Null in v0.1. |
| `totals` | Integer counts. `encountered` counts all recorded URLs, including queued and skipped URLs. `crawled` counts URLs with fetch states `fetched` or `error`. `urls` counts the crawled URLs and URLs blocked by robots.txt. `internal_urls` and `external_urls` split `urls`. `pages` counts recorded Pages. `resources` counts distinct targets of image, CSS, JavaScript, video, audio or media Links that have no Page row. |
| `status_classes` | Objects `internal` and `external`, each with integer counts `2xx`, `3xx`, `4xx`, `5xx`, `other`, `no_response`, `record_failed` and `blocked_by_robots_txt`. `other` covers codes outside 200–599. `no_response` counts requests that failed without a response. `record_failed` counts responses the Crawl could not record. A response fetched with `--ignore-robots` counts by HTTP status. |
| `indexability` | Object with integer counts `indexable` and `non_indexable` for Pages. `by_status` is an array of objects with string `status` and integer `count`, ordered by descending count and then status. |
| `content_types` | Array of objects with `content_type` (lowercase media type with parameters removed, or null), integer `count` and number `share_pct` (percentage of Internal responses, rounded to two decimal places). Order is descending count and then media type, with null last. |
| `crawl_depth` | Object. `partial` is true for Section Crawls. `max` is the highest recorded Internal depth or null. `distribution` lists integer `depth` and `count` pairs for all depths from zero through `max`, including gaps. |
| `response_time_ms` | Object for Internal responses with a recorded duration. `count` is an integer. `min`, `p50`, `p90`, `p95`, `p99` and `max` are integer milliseconds. `mean` is a number rounded to one decimal place. All six statistics and `mean` are null when `count` is zero. Percentiles use nearest rank. `histogram` has seven objects with integer `from_ms`, integer or null `to_ms` and integer `count`. The lower bound is inclusive and the upper bound is exclusive. |
| `health_score` | Object. `internal_pages` and `affected_pages` are integer counts. The latter counts distinct Internal Pages affected by at least one Issue-type Rule. `score` is the whole percentage of unaffected Internal Pages, rounded down, or null if there are none. The final Issues Pass provides all three values for completed or stopped Crawls. Other states calculate them from committed rows. All three are null when the finished Crawl predates Health recording. |
| `issues` | Object. Integer `total` counts Issues. `by_type_priority` has nine objects ordered by Issue Type (`issue`, `warning`, `opportunity`), then Priority (`high`, `medium`, `low`). Each has string `issue_type` and `priority`, integer `issues`, and integer `affected_count` summed across the Issues in the cell. `top` contains up to `--top` Issue objects in `linx issues` order, with string `rule_id`, `category`, `issue_type`, `priority` and `description`, and integer `affected_count`. |
| `segments` | Empty array in v0.1. |
| `unsegmented` | Null in v0.1. |

## Screaming Frog Overview mapping

| Overview | Crawl summary |
|---|---|
| Total URLs Encountered | `totals.encountered` |
| Total URLs Crawled | `totals.crawled` |
| Total Internal and External URLs | `totals.internal_urls` and `totals.external_urls` |
| Internal and External blocked by robots.txt | `status_classes.internal.blocked_by_robots_txt` and `status_classes.external.blocked_by_robots_txt` |
| Indexable and Non-Indexable | `indexability`, which covers recorded Pages |
| Content types and percentage of total | `content_types`, with one row per media type and a percentage of Internal responses |

## Example

```json
{
  "summary_version": 1,
  "crawl": {
    "id": "20260927-140312-k3f9",
    "seeds": ["https://example.com/"],
    "seed_count": 1,
    "crawl_mode": "spider",
    "state": "completed",
    "stop_reason": null,
    "started_at": "2026-09-27T14:03:12.345Z",
    "completed_at": "2026-09-27T14:03:12.445Z",
    "section_crawl": false,
    "link_metrics": "complete",
    "tool_version": "0.1.0",
    "schema_version": 1
  },
  "segment": null,
  "totals": {
    "encountered": 1, "crawled": 1, "urls": 1, "internal_urls": 1,
    "external_urls": 0, "pages": 1, "resources": 0
  },
  "status_classes": {
    "internal": {
      "2xx": 1, "3xx": 0, "4xx": 0, "5xx": 0, "other": 0,
      "no_response": 0, "record_failed": 0, "blocked_by_robots_txt": 0
    },
    "external": {
      "2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "other": 0,
      "no_response": 0, "record_failed": 0, "blocked_by_robots_txt": 0
    }
  },
  "indexability": {"indexable": 1, "non_indexable": 0, "by_status": []},
  "content_types": [{"content_type": "text/html", "count": 1, "share_pct": 100.0}],
  "crawl_depth": {"partial": false, "max": 0, "distribution": [{"depth": 0, "count": 1}]},
  "response_time_ms": {
    "count": 1, "min": 100, "mean": 100.0, "p50": 100, "p90": 100, "p95": 100,
    "p99": 100, "max": 100,
    "histogram": [
      {"from_ms": 0, "to_ms": 100, "count": 0},
      {"from_ms": 100, "to_ms": 250, "count": 1},
      {"from_ms": 250, "to_ms": 500, "count": 0},
      {"from_ms": 500, "to_ms": 1000, "count": 0},
      {"from_ms": 1000, "to_ms": 2000, "count": 0},
      {"from_ms": 2000, "to_ms": 5000, "count": 0},
      {"from_ms": 5000, "to_ms": null, "count": 0}
    ]
  },
  "health_score": {"score": 0, "internal_pages": 1, "affected_pages": 1},
  "issues": {
    "total": 1,
    "by_type_priority": [
      {"issue_type": "issue", "priority": "high", "issues": 1, "affected_count": 1},
      {"issue_type": "issue", "priority": "medium", "issues": 0, "affected_count": 0},
      {"issue_type": "issue", "priority": "low", "issues": 0, "affected_count": 0},
      {"issue_type": "warning", "priority": "high", "issues": 0, "affected_count": 0},
      {"issue_type": "warning", "priority": "medium", "issues": 0, "affected_count": 0},
      {"issue_type": "warning", "priority": "low", "issues": 0, "affected_count": 0},
      {"issue_type": "opportunity", "priority": "high", "issues": 0, "affected_count": 0},
      {"issue_type": "opportunity", "priority": "medium", "issues": 0, "affected_count": 0},
      {"issue_type": "opportunity", "priority": "low", "issues": 0, "affected_count": 0}
    ],
    "top": [
      {
        "rule_id": "title-missing",
        "category": "titles",
        "issue_type": "issue",
        "priority": "high",
        "affected_count": 1,
        "description": "A Page has no title, or its first title is empty."
      }
    ]
  },
  "segments": [],
  "unsegmented": null
}
```
