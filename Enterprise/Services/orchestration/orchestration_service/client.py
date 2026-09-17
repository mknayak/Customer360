from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ServiceCallError(RuntimeError):
    pass


class ServiceClient:
    def __init__(self, origins: dict[str, str]) -> None:
        self.origins = origins

    def post(self, service: str, path: str, payload: dict) -> dict:
        origin = self.origins[service]
        request = Request(
            f"{origin}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read())
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ServiceCallError(f"{service} returned {error.code}: {detail}") from error
        except URLError as error:
            raise ServiceCallError(f"{service} is unavailable: {error.reason}") from error
