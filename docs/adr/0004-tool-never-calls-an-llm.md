# The tool never calls an LLM

The tool produces deterministic data only. Interpretation comes from the AI agent that drives it.

In a Report, the numbers, charts and fix guidance come from the Crawl. The executive summary and action plan are Report Notes that the agent writes and the tool merges in. For large sites the agent spreads this work across subagents, one per Report Section, each working from its Section Brief. This keeps the tool free to run, independent of any model vendor, and testable, and every number in a Report can be traced back to crawl data.

## Considered Options

- **Built-in LLM calls with a user-supplied API key** (such as a `spider ai …` command): rejected. It duplicates what the agent already does and brings in API keys, cost and non-determinism.

## Consequences

- Anything that needs judgement, such as prioritising or explaining in terms of the specific site, belongs in the Skill's workflows, not in the tool.
- Adding LLM calls later would reverse this decision and needs a new ADR.
