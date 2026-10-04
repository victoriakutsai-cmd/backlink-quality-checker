# Backlink QA process (generic)

1. **Collect the batch.** One row per placed link: URL, who placed it, date, intended target.
2. **Screen cheap things first.** Lists and domain heuristics need no network and no paid data. Reject early.
3. **Add metrics.** Export DR, traffic and top countries from your SEO tool; use a second traffic source when the first one looks low.
4. **Crawl what is left.** Check status, indexability, link presence and correctness, duplicates, language, redirects.
5. **Review by hand what the machine cannot judge.** Blocked pages (403/429), login walls, conflicting traffic sources, possible non-English text, thin or spammy pages.
6. **Send findings back, then re-run.** Compare with the previous run: `fixed`, `still_bad`, `new_issue`. Several iterations are normal, so check new domains again each time.
7. **Track quality per author.** Share of rejected links, unique domains, average links per domain. Look for patterns, not blame.

## Design decisions
- **Order of checks = cost order.** Free checks first, crawling last.
- **One primary status, all flags kept.** The status is easy to filter on; the flags explain the rest.
- **Review is not reject.** Blocked and login-gated pages are queued for a human instead of being counted as failures.
- **Thresholds are parameters.** No built-in opinion about what a "good" domain is; set it per project.
- **The batch defines "overused".** The share threshold depends on batch size, so tune it (a small batch needs a higher percentage).
