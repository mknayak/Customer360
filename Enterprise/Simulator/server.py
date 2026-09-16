"""Local static server and same-origin proxy for the Shopping Simulator."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
CRM_ORIGIN = "http://127.0.0.1:8001"


class SimulatorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        if self.path.startswith("/crm/"):
            self._proxy("GET")
            return
        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/crm/"):
            self._proxy("POST")
            return
        self.send_error(405, "Method not allowed")

    def _proxy(self, method):
        request_body = None
        if method == "POST":
            length = int(self.headers.get("Content-Length", "0"))
            request_body = self.rfile.read(length)
        request = Request(f"{CRM_ORIGIN}{self.path[4:]}", data=request_body, method=method)
        request.add_header("Content-Type", self.headers.get("Content-Type", "application/json"))
        try:
            with urlopen(request, timeout=5) as response:
                payload = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except HTTPError as error:
            payload = error.read()
            self.send_response(error.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except URLError:
            self.send_error(503, "CRM API is unavailable")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8080), SimulatorHandler)
    print("Shopping Simulator running at http://127.0.0.1:8080")
    server.serve_forever()