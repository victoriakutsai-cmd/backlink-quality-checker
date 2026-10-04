"""Stage 1 and 2: domain-level screening. No network access here; everything is rule-based and configurable."""
import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse

TWO_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu"}


def hostname(url: str) -> str:
    return (urlparse(url.strip()).hostname or "").lower()


def registrable(host: str) -> str:
    """Naive registrable domain (handles co.uk-style suffixes). For production use a public-suffix library."""
    host = host.removeprefix("www.")
    labels = host.split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in TWO_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def load_list(path) -> set:
    """One domain per line; blank lines and lines starting with # are ignored."""
    if not path or not Path(path).exists():
        return set()
    out = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            out.add(line.removeprefix("www."))
    return out


def load_metrics(df):
    """domain -> {dr, traffic:[...], geos:[...]} from a CSV exported from any SEO tool.
    Columns: domain, dr, monthly_traffic, [monthly_traffic_2], top_geos (e.g. 'US;GB;CA')."""
    out = {}
    for _, r in df.iterrows():
        traffic = [float(r[c]) for c in ("monthly_traffic", "monthly_traffic_2") if c in df and str(r[c]) not in ("nan", "")]
        geos = [g.strip().upper() for g in str(r.get("top_geos", "")).replace(",", ";").split(";") if g.strip() and g != "nan"]
        dr = float(r["dr"]) if "dr" in df and str(r["dr"]) not in ("nan", "") else None
        out[str(r["domain"]).lower().removeprefix("www.")] = {"dr": dr, "traffic": traffic, "geos": geos}
    return out


# Flags that mean "a human should look", not "reject".
REVIEW_FLAGS = {"metrics_missing", "traffic_needs_review", "blocked_needs_manual", "login_wall", "skipped_robots", "non_english_text"}
# Rules skipped for allow-listed domains (explicit block/stop lists still apply).
METRIC_RULES = {"low_dr", "low_traffic", "geo_not_allowed", "tld_not_allowed", "free_hosting_subdomain",
                "odd_domain", "overused_domain", "metrics_missing", "traffic_needs_review"}


def domain_flags(host: str, share_pct: float, cfg: dict, lists: dict, metrics: dict) -> list:
    dom = registrable(host)
    flags = []
    if dom in lists["block"]:
        flags.append("blocklisted")
    if dom in lists["stop"]:
        flags.append("stoplisted")

    # heuristics on the host itself
    if any(host.endswith("." + s) for s in cfg["free_hosting_suffixes"]):
        flags.append("free_hosting_subdomain")
    tld = host.rsplit(".", 1)[-1]
    if not is_ip(host) and len(tld) == 2 and tld not in cfg["allowed_cctlds"]:
        flags.append("tld_not_allowed")
    if (cfg.get("treat_ip_hosts_as_odd", True) and is_ip(host)) or host.startswith("xn--") or ".xn--" in host or re.search(r"[^\x00-\x7f]", host):
        flags.append("odd_domain")
    if share_pct > cfg["max_domain_share_pct"]:
        flags.append("overused_domain")

    # metrics
    m = metrics.get(dom) or metrics.get(host)
    if m is None:
        flags.append("metrics_missing")
    else:
        if m["dr"] is not None and m["dr"] < cfg["min_dr"]:
            flags.append("low_dr")
        if m["traffic"]:
            low = [t < cfg["min_monthly_traffic"] for t in m["traffic"]]
            if all(low):
                flags.append("low_traffic")          # confirmed by every source we have
            elif any(low):
                flags.append("traffic_needs_review")  # sources disagree
        if m["geos"] and not set(m["geos"][: cfg["geo_top_n"]]) & set(cfg["allowed_geos"]):
            flags.append("geo_not_allowed")

    if dom in lists["allow"]:
        flags = [f for f in flags if f not in METRIC_RULES]
    return flags
