"""Local static server and same-origin proxy for the Shopping Simulator."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
CRM_ORIGIN = "http://127.0.0.1:8001"
PRODUCT_ORIGIN = "http://127.0.0.1:8002"
SHOPPING_ORIGIN = "http://127.0.0.1:8003"
SITE_ORIGIN = "http://127.0.0.1:8004"
FEEDBACK_ORIGIN = "http://127.0.0.1:8005"
MARKETING_ORIGIN = "http://127.0.0.1:8006"
EVENTS_ORIGIN = "http://127.0.0.1:8007"
ORCHESTRATION_ORIGIN = "http://127.0.0.1:8008"
DATA_PLATFORM_ORIGIN = "http://127.0.0.1:8010"


PROXY_ORIGINS = {
    "crm": CRM_ORIGIN,
    "product": PRODUCT_ORIGIN,
    "shopping": SHOPPING_ORIGIN,
    "site": SITE_ORIGIN,
    "feedback": FEEDBACK_ORIGIN,
    "marketing": MARKETING_ORIGIN,
    "events": EVENTS_ORIGIN,
    "orchestration": ORCHESTRATION_ORIGIN,
    "data-platform": DATA_PLATFORM_ORIGIN,
}


class SimulatorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        if self._is_service_path():
            self._proxy("GET")
            return
        super().do_GET()

    def do_POST(self):
        if self._is_service_path():
            self._proxy("POST")
            return
        self.send_error(405, "Method not allowed")

    def do_PUT(self):
        if self._is_service_path():
            self._proxy("PUT")
            return
        self.send_error(405, "Method not allowed")

    def do_DELETE(self):
        if self._is_service_path():
            self._proxy("DELETE")
            return
        self.send_error(405, "Method not allowed")

    def _is_service_path(self):
        return any(self.path.startswith(f"/{prefix}/") for prefix in PROXY_ORIGINS)

    def _proxy(self, method):
        request_body = None
        if method in {"POST", "PUT"}:
            length = int(self.headers.get("Content-Length", "0"))
            request_body = self.rfile.read(length)
        prefix = self.path.split("/", 2)[1]
        origin = PROXY_ORIGINS[prefix]
        request = Request(f"{origin}{self.path[len(prefix) + 1:]}", data=request_body, method=method)
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
            self.send_error(503, f"{prefix.title()} API is unavailable")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8080), SimulatorHandler)
    print("Shopping Simulator running at http://127.0.0.1:8080")
    server.serve_forever()