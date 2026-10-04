# Backlink quality checker

![tests](https://github.com/victoriakutsai-cmd/backlink-quality-checker/actions/workflows/tests.yml/badge.svg)

Screens a batch of placed backlinks in three cheap-to-expensive stages and tells you, for every link, **why it passed or failed**.

> **Portfolio project written from scratch on synthetic data.** It contains no data, lists, names, thresholds or code from any employer or client. All domains are fictional (`.example`, documentation IP range), authors are placeholders, and every quality threshold is a configurable parameter you set yourself.

## Why

Links that get placed for a site are often wrong in boring ways: the domain is weak, the audience is in the wrong country, the page is `noindex`, the link was removed, the page links to the target twice. Checking this by hand takes hours and is inconsistent. This tool applies the same rules to every link, in the same order, and records the reason.

## How it works

```
links.csv ──► 1. Domain rules (no network) ──► 2. Metrics rules (from your SEO tool export) ──► 3. Page checks (crawl)
              block / stop / allow lists         DR, traffic, top countries                      status, noindex, link present,
              free hosting, odd domains,                                                          extra links, language, redirects
              country TLDs, overused domains
```

Stage 3 only runs for links that were **not** already rejected in stages 1–2, which saves requests and time.

| Stage | Checks | Network |
|---|---|---|
| 1. Domain rules | block list, stop list, free-hosting subdomains, country TLDs outside your target markets, IP or non-ASCII hosts, domains that make up too large a share of the batch | no |
| 2. Metrics | minimum DR, minimum traffic (confirmed by one or two sources), top countries, missing metrics | no (CSV input) |
| 3. Page checks | HTTP status and redirect chain, `noindex` (meta and `X-Robots-Tag`), target link present / clickable / correct URL / duplicated, title and H1 language, login walls, blocked pages | yes (robots.txt respected, per-host throttling) |

Every link gets one **primary status** (first matching rule in `priority`) and a **severity**: `ok`, `reject` or `review` (a human should look: blocked pages, login walls, conflicting traffic sources, missing metrics, possible non-English text). `all_flags` keeps every problem found.

## Quick start

```bash
pip install -r requirements.txt
python tools/make_sample_data.py          # synthetic links, metrics and example lists
python -m backlink_checker --links data/links.sample.csv --metrics data/domain_metrics.sample.csv \
       --config config.example.json --no-crawl -o output
```

Remove `--no-crawl` to also fetch pages (use your own list of real URLs and set `target_domain` in the config).
Re-run after fixes and compare with the previous run: `--previous output_old/report.csv` writes `iteration_diff.csv` (`fixed`, `still_bad`, `new_issue`, ...).

### Inputs
- `--links`: `link_url, author[, post_date, target_url]`
- `--metrics`: `domain, dr, monthly_traffic[, monthly_traffic_2], top_geos` (for example `US;GB;CA`), exported from any SEO tool
- `lists/blocklist.txt`, `stoplist.txt`, `allowlist.txt`: one domain per line (allow-listed domains skip metric and heuristic rules; block and stop lists still apply)
- `config.example.json`: thresholds, allowed countries and TLDs, crawl settings

### Outputs
- `report.csv`: one row per link with status, severity, all flags, HTTP status, redirect chain, title, H1, anchor, rel
- `summary_by_author.csv`: links, unique domains, average links per domain, share rejected / needs review / good
- `iteration_diff.csv` (with `--previous`)

### Example (synthetic data, screening only)

Full sample output: [`docs/sample_report.csv`](docs/sample_report.csv) and [`docs/sample_summary_by_author.csv`](docs/sample_summary_by_author.csv).

| author | links | unique_domains | pct_blocklisted | pct_stoplisted | pct_other_rejected | pct_good |
|---|---|---|---|---|---|---|
| author_a | 31 | 22 | 0.0 | 0.0 | 6.5 | 90.3 |
| author_b | 37 | 9 | 16.2 | 10.8 | 56.8 | 16.2 |
| author_c | 22 | 16 | 4.5 | 0.0 | 13.6 | 72.7 |

## Tests

```bash
python -m unittest -v
```
Run locally on Python 3.9 (Windows) and 3.12; CI runs the same tests on 3.9 and 3.12 for every commit.
12 tests: domain rules, priority and severity, a local test server with 12 page scenarios (ok, redirect, link missing, plain-text URL, noindex via meta and header, duplicate links, wrong URL, non-English title, 404, 403, login wall), "rejected domains are not crawled", iteration diff, author summary.

## Limitations (honest list)
- Registrable-domain detection is naive (handles `co.uk`-style suffixes); use a public-suffix library for production.
- Language check is a cheap heuristic that queues pages for review, not a language detector.
- No JavaScript rendering: links injected by scripts are not seen.
- Metrics come from a CSV; there are no API integrations.
- Tested on a local test server and synthetic data, not on the live internet.
- Spam judgement (for example thin pages with no real comments) stays manual.

MIT licence.
