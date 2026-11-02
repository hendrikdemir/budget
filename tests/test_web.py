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
