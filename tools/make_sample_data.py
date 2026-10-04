"""Generate fully synthetic sample data: placed links, domain metrics, and example lists.
All domains are fictional (.example, documentation IP range, or clearly fake names). Authors are placeholders."""
import random
from pathlib import Path

import pandas as pd

rng = random.Random(11)
ROOT = Path(__file__).resolve().parent.parent

GOOD = [f"site-{i:02d}.example" for i in range(1, 31)]
SPECIAL = {
    "low-dr-demo.example": dict(dr=8, t=[4000], geos="US;GB"),
    "low-traffic-demo.example": dict(dr=30, t=[120, 90], geos="US;CA"),
    "traffic-disagree-demo.example": dict(dr=35, t=[300, 4200], geos="US;AU"),
    "wrong-geo-demo.example": dict(dr=40, t=[9000], geos="IN;PK;BD"),
    "synthetic-demo-01.wordpress.com": dict(dr=45, t=[3000], geos="US;GB"),
    "forum-demo.xx": dict(dr=40, t=[3000], geos="US;GB"),
    "203.0.113.7": dict(dr=30, t=[2000], geos="US;GB"),
    "blocked-demo.example": dict(dr=50, t=[8000], geos="US;GB"),
    "stopped-demo.example": dict(dr=50, t=[8000], geos="US;GB"),
    "overused-demo.example": dict(dr=42, t=[7000], geos="US;GB"),
}
metrics = [dict(domain=d, dr=rng.randint(25, 62), monthly_traffic=rng.randint(1500, 60000), top_geos=rng.choice(["US;GB;CA", "US;AU;GB", "GB;US;IE", "CA;US;GB"])) for d in GOOD]
for d, v in SPECIAL.items():
    row = dict(domain=d, dr=v["dr"], monthly_traffic=v["t"][0], top_geos=v["geos"])
    if len(v["t"]) > 1:
        row["monthly_traffic_2"] = v["t"][1]
    metrics.append(row)
pd.DataFrame(metrics).to_csv(ROOT / "data" / "domain_metrics.sample.csv", index=False)

def url(d, i):
    return f"https://{d}/thread/{rng.randint(1000, 99999)}-{i}"

rows = []
plan = {
    "author_a": [(GOOD, 28), (["low-dr-demo.example"], 1), (["forum-demo.xx"], 1), (["no-metrics-demo.example"], 1)],
    "author_b": [(["overused-demo.example"], 14), (["blocked-demo.example"], 6), (["stopped-demo.example"], 4),
                 (GOOD[:3], 6), (["low-traffic-demo.example"], 3), (["wrong-geo-demo.example"], 2), (["synthetic-demo-01.wordpress.com"], 2)],
    "author_c": [(GOOD, 16), (["traffic-disagree-demo.example"], 2), (["203.0.113.7"], 1), (["low-dr-demo.example"], 2), (["blocked-demo.example"], 1)],
}
i = 0
for author, parts in plan.items():
    for pool, n in parts:
        for _ in range(n):
            i += 1
            d = rng.choice(pool)
            rows.append(dict(link_url=url(d, i), author=author, post_date=f"2026-09-{rng.randint(1, 28):02d}", target_url="https://client.example/page"))
rng.shuffle(rows)
pd.DataFrame(rows).to_csv(ROOT / "data" / "links.sample.csv", index=False)

(ROOT / "lists").mkdir(exist_ok=True)
(ROOT / "lists" / "blocklist.txt").write_text("# Domains you never want links from (synthetic examples)\nblocked-demo.example\n")
(ROOT / "lists" / "stoplist.txt").write_text("# Domains paused for now, e.g. overused or under review (synthetic examples)\nstopped-demo.example\n")
(ROOT / "lists" / "allowlist.txt").write_text("# Trusted domains: skip metric and heuristic rules (explicit block/stop lists still apply)\nsite-03.example\n")
print(f"{len(rows)} synthetic links, {len(metrics)} metric rows")
