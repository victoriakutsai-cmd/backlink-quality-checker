"""Run the three stages and assign one primary status per link."""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from .crawl import Robots, Throttle, check_page
from .screening import REVIEW_FLAGS, domain_flags, hostname, registrable

DEFAULT_CFG = {
    "target_domain": "client.example",
    "min_dr": 15,
    "min_monthly_traffic": 500,
    "allowed_geos": ["US", "GB", "CA", "IE"],
    "geo_top_n": 3,
    "allowed_cctlds": ["us", "uk", "ca", "au", "nz", "ie"],
    "free_hosting_suffixes": ["wordpress.com", "blogspot.com", "wixsite.com", "weebly.com", "tumblr.com"],
    "max_domain_share_pct": 5.0,
    "treat_ip_hosts_as_odd": True,
    "priority": ["blocklisted", "stoplisted", "low_dr", "low_traffic", "geo_not_allowed", "free_hosting_subdomain",
                 "tld_not_allowed", "odd_domain", "overused_domain", "http_error", "noindex", "link_missing",
                 "link_not_clickable", "wrong_target_url", "extra_target_links", "non_english_text", "login_wall",
                 "blocked_needs_manual", "metrics_missing", "traffic_needs_review", "skipped_robots"],
    "crawl": {"workers": 8, "timeout": 10, "delay": 0.5, "respect_robots": True,
              "user_agent": "backlink-quality-checker/0.1 (portfolio project)"},
}


def merge_cfg(user: dict) -> dict:
    cfg = {**DEFAULT_CFG, **user}
    cfg["crawl"] = {**DEFAULT_CFG["crawl"], **user.get("crawl", {})}
    return cfg


def primary(flags, priority):
    if not flags:
        return "ok", "ok"
    top = sorted(flags, key=lambda f: priority.index(f) if f in priority else 999)[0]
    return top, ("review" if top in REVIEW_FLAGS else "reject")


def run(links: pd.DataFrame, cfg: dict, lists: dict, metrics: dict, crawl: bool = True) -> pd.DataFrame:
    df = links.copy().reset_index(drop=True)
    df["host"] = df.link_url.map(hostname)
    df["domain"] = df.host.map(registrable)
    share = (df.domain.value_counts() / len(df) * 100).to_dict()

    # stage 1-2: domain rules (cached per host)
    cache = {h: domain_flags(h, share[registrable(h)], cfg, lists, metrics) for h in df.host.unique()}
    flags = [list(cache[h]) for h in df.host]
    det = [dict.fromkeys(("http_status", "redirect_chain", "title", "h1", "target_links", "anchor", "rel"), "") for _ in range(len(df))]

    # stage 3: crawl only links that were not already rejected on domain rules
    if crawl:
        todo = [i for i, f in enumerate(flags) if primary(f, cfg["priority"])[1] != "reject"]
        session = requests.Session()
        session.headers["User-Agent"] = cfg["crawl"]["user_agent"]
        th, rb = Throttle(cfg["crawl"]["delay"]), Robots(cfg["crawl"]["user_agent"])
        rows = df.to_dict("records")
        with ThreadPoolExecutor(cfg["crawl"]["workers"]) as ex:
            results = list(ex.map(lambda i: check_page(rows[i], cfg, session, th, rb), todo))
        for i, (fl, d) in zip(todo, results):
            flags[i] += fl
            det[i] = d

    st = [primary(f, cfg["priority"]) for f in flags]
    df["status"], df["severity"] = [s[0] for s in st], [s[1] for s in st]
    df["all_flags"] = [";".join(f) for f in flags]
    return pd.concat([df, pd.DataFrame(det)], axis=1)


def summary_by_author(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("author")
    out = pd.DataFrame({
        "links": g.size(),
        "unique_domains": g.domain.nunique(),
        "pct_blocklisted": g.apply(lambda x: (x.status == "blocklisted").mean() * 100, include_groups=False),
        "pct_stoplisted": g.apply(lambda x: (x.status == "stoplisted").mean() * 100, include_groups=False),
        "pct_other_rejected": g.apply(lambda x: ((x.severity == "reject") & ~x.status.isin(["blocklisted", "stoplisted"])).mean() * 100, include_groups=False),
        "pct_needs_review": g.apply(lambda x: (x.severity == "review").mean() * 100, include_groups=False),
        "good_links": g.apply(lambda x: int((x.status == "ok").sum()), include_groups=False),
    })
    out["avg_links_per_domain"] = out.links / out.unique_domains
    out["pct_good"] = out.good_links / out.links * 100
    return out.round(1).reset_index()


def iteration_diff(prev: pd.DataFrame, cur: pd.DataFrame) -> pd.DataFrame:
    """Compare two runs of the same batch: which problems were fixed and which remain."""
    m = prev[["link_url", "status"]].rename(columns={"status": "previous_status"}).merge(
        cur[["link_url", "status"]].rename(columns={"status": "current_status"}), on="link_url", how="outer")

    def change(r):
        if pd.isna(r.previous_status):
            return "new_link" if r.current_status == "ok" else "new_link_with_issue"
        if pd.isna(r.current_status):
            return "removed_from_batch"
        if r.previous_status != "ok" and r.current_status == "ok":
            return "fixed"
        if r.previous_status != "ok" and r.current_status == r.previous_status:
            return "still_bad"
        if r.previous_status != "ok":
            return "different_issue"
        return "new_issue" if r.current_status != "ok" else "unchanged_ok"
    m["change"] = m.apply(change, axis=1)
    return m
