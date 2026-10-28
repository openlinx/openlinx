# SEO Spider

An agent-first website crawler that audits sites for technical SEO problems. AI agents drive it and turn its data into Reports for people.

## Language

### Crawling

**Workspace**:
The place where one project's Crawls and settings live, usually one per client or site.
_Avoid_: project, folder

**Crawl**:
One run of the spider over a site or a URL list, together with everything it recorded.
_Avoid_: scan, audit, job

**Crawl Mode**:
How a Crawl finds URLs: *Spider* (follow Links from the Seed), *List* (a given set of URLs) or *Sitemap* (the URLs listed in XML sitemaps).
_Avoid_: crawl type

**Crawl State**:
Where a Crawl stands: *running*, *stopped* (paused, resumable), *completed* (ran to the end), *failed* (could not continue, resumable) or *interrupted* (its process died, resumable).
_Avoid_: finished, done, status (for this meaning)

**Seed**:
The URL or URLs a Crawl starts from.
_Avoid_: start URL, root

**Scope**:
The rule that decides which discovered URLs a Crawl follows. URLs outside the Scope may still be checked, but they are never followed.
_Avoid_: boundary, crawl filter

**Section Crawl**:
A Crawl whose Scope is limited to one part of a site, such as a subfolder. Its link metrics are partial.
_Avoid_: partial crawl, section

**Segment**:
A named subset of a Crawl's Pages, defined by conditions on their data. A Page belongs to at most one Segment.
_Avoid_: section, group, category

**Hand-off**:
When an agent gives the user a ready-to-run Command (usually a large Crawl) and does not run it itself.
_Avoid_: delegation

### URLs, Pages and Links

**URL**:
An address the Crawl discovered, together with how it responded.
_Avoid_: link, page

**Internal URL**:
A URL that belongs to the crawled site under the Scope's host rules. Every other URL is an **External URL**.
_Avoid_: on-site, off-site

**Page**:
A URL that returned an HTML document, together with the SEO data extracted from it.
_Avoid_: document

**Resource**:
A non-HTML file that a Page references, such as an image, stylesheet or script. It is checked for status and size but not analysed as a Page.
_Avoid_: asset

**Checked URL**:
A URL that a Crawl requests for its response without following it: an External URL, a URL outside the Scope, or one that a Page references as a Resource, unless it is in-Scope HTML, whose Links are then followed.
_Avoid_: check

**Link**:
A reference from a Page to a URL (anchor, image, canonical, hreflang, …), with its attributes. Seen from the target it is an **Inlink**; seen from the source it is an **Outlink**.
_Avoid_: href, reference
In code, a _reference_ is only the raw string of an attribute or a header before it resolves to a Link, as the URL Standard names it (`spider.crawl.references`).

**Redirect Chain**:
The hops from a URL to its final destination, each with its own status.
_Avoid_: redirect path

**Crawl Depth**:
The number of Links followed from the Seed to reach a URL.
_Avoid_: click depth, level

**Indexability**:
Whether search engines are allowed to index a URL: *Indexable* or *Non-Indexable*. The **Indexability Status** gives the reason when it is not, such as noindex, canonicalised, blocked by robots.txt or a non-2xx response.
_Avoid_: indexation (that is what a search engine did, not what the page allows)

### Content

**Content Area**:
The part of a Page counted as its content for word counts and duplicate detection. By default it leaves out navigation, header and footer.
_Avoid_: body, main content

**Exact Duplicate**:
A Page whose Content Area is identical to another Page's.
_Avoid_: copy

**Near-Duplicate**:
A Page whose Content Area is highly similar to another Page's (90% or more by default) but not identical.
_Avoid_: similar page, thin duplicate

**Custom Extraction**:
A user-defined rule that pulls extra values out of every Page into extra columns.
_Avoid_: scraping, extractor

### Analysis

**Rule**:
A deterministic check with fixed guidance (description, why it matters, how to fix), an Issue Type, a Priority and adjustable thresholds.
_Avoid_: check, test, audit

**Issue**:
A Rule that fired in a Crawl, together with the URLs it affects.
_Avoid_: error, problem, finding

**Affected URL**:
One URL that an Issue applies to.
_Avoid_: occurrence, hit

**Issue Type**:
How certain the problem is: *Issue* (definitely wrong), *Warning* (needs checking) or *Opportunity* (could be improved).
_Avoid_: severity

**Priority**:
How urgently an Issue should be fixed: *High*, *Medium* or *Low*.
_Avoid_: importance, impact

**Link Score**:
A 0–100 measure of a Page's internal link authority, calculated from the Links between Internal URLs.
_Avoid_: PageRank, internal PR

**Health Score**:
The percentage of Internal Pages that are not an Affected URL of any Issue whose Issue Type is *Issue*.
_Avoid_: site score, audit score

**Crawl Diff**:
A comparison of two Crawls of the same site that shows new, fixed and changed URLs and Issues.
_Avoid_: comparison, delta

### Reporting

**Report**:
The self-contained document built from a Crawl for people. It combines the Crawl's data with the agent's Report Notes.
_Avoid_: export, dashboard

**Report Section**:
A fixed part of a Report that covers one topic (for example titles or indexability) or one Segment.
_Avoid_: chapter, section

**Section Brief**:
The compact data for one Report Section, given to an agent to analyse.
_Avoid_: digest, section summary

**Report Notes**:
The agent's written analysis, one per Report Section plus an executive summary, which the tool merges into a Report.
_Avoid_: AI summary, comments

### Agent interface

**Command**:
One operation the tool offers to agents and people, such as crawl, issues or report. It is available on the command line and, where it makes sense, as an MCP tool.
_Avoid_: task, action

**Skill**:
The packaged instructions that teach an AI agent when and how to use the Commands.
_Avoid_: plugin, prompt

## Flagged ambiguities

- **"Task"**: the user's early wording meant **Command**.
- **"Finished"**: say which Crawl State you mean. *completed* means the Crawl ran to the end. The work done after a Crawl ends as *completed* or *stopped* is the "post-crawl passes".
- **"Section"**: never use it alone. Say **Section Crawl** (crawling part of a site), **Segment** (analysing part of a Crawl) or **Report Section** (part of a Report).
- **"Language"** can mean the language a Page declares or the language detected from its text. They can differ, so name which one you mean.
- **"Issue"** is both the concept and one of the Issue Type values, a naming inherited from Screaming Frog. "An Issue of type Warning" is fine. For the first value, write "an *Issue*-type Issue".
