"""The declared public schema of a crawl file (design D6 of 015-add-crawl-store)."""

from sqlalchemy import MetaData

# The only definition of the public schema; each change adds its tables here.
metadata = MetaData()
