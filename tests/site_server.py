"""Tiny local server with one page per scenario, so the crawl stage can be tested offline."""
import http.server
import socketserver
import threading

T = "https://client.example/page"
PAGES = {
    "/ok": f"<title>A guide to the best tools for you</title><h1>A guide to the best tools</h1><a href='{T}'>best tools</a>",
    "/missing": "<title>A guide to the best tools for you</title><p>No link here.</p>",
    "/plain": "<title>A guide to the best tools for you</title><p>Visit client.example for more.</p>",
    "/noindex": f"<title>A guide to the best tools for you</title><meta name='robots' content='noindex'><a href='{T}'>tools</a>",
    "/extra": f"<title>A guide to the best tools for you</title><a href='{T}'>one</a> <a href='https://client.example/other'>two</a>",
    "/wrong": "<title>A guide to the best tools for you</title><a href='https://client.example/other'>tools</a>",
    "/ru": f"<title>Лучшие инструменты для вашего бизнеса</title><h1>Обзор</h1><a href='{T}'>tools</a>",
    "/login": "<title>Sign in</title>",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body="", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        p = self.path
        if p == "/robots.txt":
            return self._send(200, "User-agent: *\nDisallow: /private\n")
        if p == "/404":
            return self._send(404, "gone")
        if p == "/forbidden":
            return self._send(403, "captcha")
        if p == "/login-wall":
            return self._send(302, "", {"Location": "/login"})
        if p == "/moved":
            return self._send(301, "", {"Location": "/ok"})
        if p == "/xrobots":
            return self._send(200, PAGES["/ok"], {"X-Robots-Tag": "noindex"})
        if p in PAGES:
            return self._send(200, PAGES[p])
        self._send(404, "not found")


def start():
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]
