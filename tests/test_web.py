"""The server only answers the app's own page, not websites open in a browser."""
import http.client
import json
import threading

from app.web import make_server

from .base import AppTest


class OnlyTheApp(AppTest):
    def setUp(self):
        super().setUp()
        self.server = make_server(0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def request(self, method, path, body=None, **headers):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        response.read()
        conn.close()
        return response.status

    def post(self, path, **headers):
        return self.request("POST", path, json.dumps({"theme": "dark"}), **{"Content-Type": "application/json", **headers})

    def test_the_app_itself(self):
        self.assertEqual(self.request("GET", "/"), 200)
        self.assertEqual(self.request("GET", "/api/version"), 200)
        self.assertEqual(self.post("/api/settings", Origin=f"http://127.0.0.1:{self.port}"), 200)
        self.assertEqual(self.post("/api/settings", Host=f"localhost:{self.port}", Origin=f"http://localhost:{self.port}"), 200)

    def test_another_website_cant_send_changes(self):
        self.assertEqual(self.post("/api/settings", Origin="https://example.com"), 403)

    def test_forms_and_plain_text_are_refused(self):
        body = json.dumps({"ids": [1]})
        self.assertEqual(self.request("POST", "/api/transactions-delete", body, **{"Content-Type": "text/plain"}), 403)

    def test_another_domain_pointed_here_cant_read(self):
        self.assertEqual(self.request("GET", "/api/export", Host=f"example.com:{self.port}"), 403)
        self.assertEqual(self.request("GET", "/", Host="example.com"), 403)


class OnlyTheWindowWithTheKey(AppTest):
    """The desktop app's server answers only the window it gave its key to."""

    def setUp(self):
        super().setUp()
        self.server = make_server(0, key="s3cret")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def get(self, path, **headers):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        response.read()
        conn.close()
        return response

    def test_without_the_cookie_the_api_refuses(self):
        self.assertEqual(self.get("/api/version").status, 403)
        self.assertEqual(self.get("/api/version", Cookie="budget_key=guess").status, 403)
        self.assertEqual(self.get("/").status, 200)  # the page itself holds no data

    def test_the_key_becomes_a_cookie_only_the_window_has(self):
        self.assertEqual(self.get("/?key=wrong").status, 403)
        response = self.get("/?key=s3cret")
        self.assertEqual((response.status, response.getheader("Location")), (303, "/"))
        cookie = response.getheader("Set-Cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertEqual(self.get("/api/version", Cookie=cookie.split(";")[0]).status, 200)

    def test_safety_headers_and_no_listings(self):
        response = self.get("/")
        self.assertIn("script-src 'self'", response.getheader("Content-Security-Policy"))
        self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(self.get("/js/").status, 404)
