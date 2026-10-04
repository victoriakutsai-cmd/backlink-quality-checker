import unittest

import pandas as pd

from backlink_checker.pipeline import iteration_diff, merge_cfg, primary, run, summary_by_author
from backlink_checker.screening import domain_flags, load_metrics, registrable
from tests.site_server import start

CFG = merge_cfg({"target_domain": "client.example", "crawl": {"delay": 0, "workers": 4}})
NOLISTS = {"block": set(), "stop": set(), "allow": set()}
METRICS = load_metrics(pd.DataFrame([
    dict(domain="good.example", dr=40, monthly_traffic=5000, top_geos="US;GB"),
    dict(domain="lowdr.example", dr=5, monthly_traffic=5000, top_geos="US;GB"),
    dict(domain="lowtraffic.example", dr=40, monthly_traffic=100, monthly_traffic_2=80, top_geos="US;GB"),
    dict(domain="disagree.example", dr=40, monthly_traffic=100, monthly_traffic_2=9000, top_geos="US;GB"),
    dict(domain="geo.example", dr=40, monthly_traffic=5000, top_geos="IN;PK;BD"),
    dict(domain="localhost", dr=50, monthly_traffic=5000, top_geos="US"),
]))


class Screening(unittest.TestCase):
    def flags(self, host, share=1.0, lists=NOLISTS, cfg=CFG):
        return domain_flags(host, share, cfg, lists, METRICS)

    def test_good_domain_has_no_flags(self):
        self.assertEqual(self.flags("good.example"), [])

    def test_metric_rules(self):
        self.assertIn("low_dr", self.flags("lowdr.example"))
        self.assertIn("low_traffic", self.flags("lowtraffic.example"))
        self.assertIn("traffic_needs_review", self.flags("disagree.example"))
        self.assertIn("geo_not_allowed", self.flags("geo.example"))
        self.assertIn("metrics_missing", self.flags("unknown.example"))

    def test_heuristics(self):
        self.assertIn("free_hosting_subdomain", self.flags("demo.wordpress.com"))
        self.assertIn("tld_not_allowed", self.flags("forum.xx"))
        self.assertNotIn("tld_not_allowed", self.flags("forum.co.uk"))
        self.assertIn("odd_domain", self.flags("203.0.113.7"))
        self.assertIn("odd_domain", self.flags("xn--80ak6aa92e.example"))
        self.assertIn("overused_domain", self.flags("good.example", share=12))

    def test_lists(self):
        lists = {"block": {"good.example"}, "stop": set(), "allow": set()}
        self.assertIn("blocklisted", self.flags("good.example", lists=lists))
        allow = {"block": set(), "stop": set(), "allow": {"lowdr.example"}}
        self.assertEqual(self.flags("lowdr.example", lists=allow), [])  # allowlist skips metric rules

    def test_registrable(self):
        self.assertEqual(registrable("www.a.b.example.co.uk"), "example.co.uk")
        self.assertEqual(registrable("forum.example.com"), "example.com")

    def test_priority_and_severity(self):
        self.assertEqual(primary(["noindex", "low_dr"], CFG["priority"]), ("low_dr", "reject"))
        self.assertEqual(primary(["login_wall"], CFG["priority"]), ("login_wall", "review"))
        self.assertEqual(primary([], CFG["priority"]), ("ok", "ok"))


class Crawl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, port = start()
        base = f"http://localhost:{port}"
        cfg = merge_cfg({"target_domain": "client.example", "max_domain_share_pct": 100, "crawl": {"delay": 0, "workers": 4}})
        cases = {"/ok": "ok", "/moved": "ok", "/missing": "link_missing", "/plain": "link_not_clickable", "/noindex": "noindex",
                 "/xrobots": "noindex", "/extra": "extra_target_links", "/wrong": "wrong_target_url", "/ru": "non_english_text",
                 "/404": "http_error", "/forbidden": "blocked_needs_manual", "/login-wall": "login_wall"}
        cls.cases = cases
        links = pd.DataFrame({"link_url": [base + p for p in cases], "author": "author_a",
                              "target_url": "https://client.example/page"})
        cls.rep = run(links, cfg, NOLISTS, METRICS)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_every_scenario_gets_expected_status(self):
        got = dict(zip(self.rep.link_url.str.replace(r"http://localhost:\d+", "", regex=True), self.rep.status))
        for path, expected in self.cases.items():
            self.assertEqual(got[path], expected, path)

    def test_review_vs_reject(self):
        sev = dict(zip(self.rep.status, self.rep.severity))
        self.assertEqual(sev["login_wall"], "review")
        self.assertEqual(sev["blocked_needs_manual"], "review")
        self.assertEqual(sev["link_missing"], "reject")

    def test_redirect_chain_recorded(self):
        row = self.rep[self.rep.link_url.str.endswith("/moved")].iloc[0]
        self.assertEqual(row.redirect_chain, "301>200")

    def test_rejected_domains_are_not_crawled(self):
        cfg = merge_cfg({"target_domain": "client.example"})
        links = pd.DataFrame({"link_url": ["https://lowdr.example/a"], "author": "x"})
        rep = run(links, cfg, NOLISTS, METRICS)
        self.assertEqual(rep.status.iloc[0], "low_dr")
        self.assertEqual(str(rep.http_status.iloc[0]), "")  # no request made


class Reports(unittest.TestCase):
    def test_iteration_diff(self):
        prev = pd.DataFrame({"link_url": ["a", "b", "c", "d"], "status": ["noindex", "link_missing", "ok", "low_dr"]})
        cur = pd.DataFrame({"link_url": ["a", "b", "c", "e"], "status": ["ok", "link_missing", "http_error", "ok"]})
        d = dict(zip(iteration_diff(prev, cur).link_url, iteration_diff(prev, cur).change))
        self.assertEqual(d, {"a": "fixed", "b": "still_bad", "c": "new_issue", "d": "removed_from_batch", "e": "new_link"})

    def test_author_summary(self):
        rep = pd.DataFrame({"author": ["a", "a", "b"], "domain": ["x", "y", "x"], "status": ["ok", "blocklisted", "ok"],
                            "severity": ["ok", "reject", "ok"]})
        s = summary_by_author(rep).set_index("author")
        self.assertEqual(s.loc["a", "links"], 2)
        self.assertEqual(s.loc["a", "pct_blocklisted"], 50.0)
        self.assertEqual(s.loc["b", "pct_good"], 100.0)


if __name__ == "__main__":
    unittest.main()
