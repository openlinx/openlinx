"""Share the SQL result and time limits and their hints across entry points."""

DEFAULT_SQL_LIMIT = 1_000
MAX_SQL_LIMIT = 100_000
DEFAULT_SQL_TIMEOUT = 30.0
SQL_LIMIT_HINT = f"Use --limit with an integer from 1 to {MAX_SQL_LIMIT:,}."
SQL_TIMEOUT_HINT = "Use --timeout with a finite nonnegative number of seconds."
