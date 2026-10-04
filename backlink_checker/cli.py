import argparse
import json
from pathlib import Path

import pandas as pd

from .pipeline import iteration_diff, merge_cfg, run, summary_by_author
from .screening import load_list, load_metrics


def main(argv=None):
    ap = argparse.ArgumentParser(prog="backlink_checker", description="Screen and verify placed backlinks.")
    ap.add_argument("--links", required=True, help="CSV: link_url, author[, post_date, target_url]")
    ap.add_argument("--metrics", help="CSV: domain, dr, monthly_traffic[, monthly_traffic_2], top_geos")
    ap.add_argument("--config", help="JSON config (see config.example.json)")
    ap.add_argument("--lists", default="lists", help="folder with blocklist.txt, stoplist.txt, allowlist.txt")
    ap.add_argument("--previous", help="report.csv from an earlier iteration, to see what was fixed")
    ap.add_argument("--no-crawl", action="store_true", help="domain screening only, no network requests")
    ap.add_argument("-o", "--out", default="output")
    a = ap.parse_args(argv)

    cfg = merge_cfg(json.loads(Path(a.config).read_text()) if a.config else {})
    ld = Path(a.lists)
    lists = {k: load_list(ld / f"{k}list.txt") for k in ("block", "stop", "allow")}
    metrics = load_metrics(pd.read_csv(a.metrics)) if a.metrics else {}
    links = pd.read_csv(a.links)
    if "author" not in links:
        links["author"] = "unknown"

    rep = run(links, cfg, lists, metrics, crawl=not a.no_crawl)
    out = Path(a.out)
    out.mkdir(exist_ok=True)
    rep.to_csv(out / "report.csv", index=False)
    summary_by_author(rep).to_csv(out / "summary_by_author.csv", index=False)
    print(f"{len(rep)} links | ok: {(rep.status == 'ok').sum()} | rejected: {(rep.severity == 'reject').sum()} | needs review: {(rep.severity == 'review').sum()}")
    print(rep.status.value_counts().to_string())
    if a.previous:
        diff = iteration_diff(pd.read_csv(a.previous), rep)
        diff.to_csv(out / "iteration_diff.csv", index=False)
        print("\niteration diff:\n" + diff.change.value_counts().to_string())


if __name__ == "__main__":
    main()
