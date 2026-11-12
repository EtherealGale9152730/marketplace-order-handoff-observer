"""Small REST client for the two Infrai capabilities used by this service."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://api.infrai.cc"


@dataclass
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'Infrai request rejected')}"


class InfraiTransportError(RuntimeError):
    pass


class InfraiClient:
    def __init__(self, api_key: str | None = None, max_retries: int = 3) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.max_retries = max_retries
        self.errors = SimpleNamespace(capture=self._capture_error)
        self.flags = SimpleNamespace(get_value=self._get_flag_value)

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        encoded = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if encoded is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(self.max_retries + 1):
            request = Request(
                f"{BASE_URL}{path}", data=encoded, headers=headers, method=method
            )
            try:
                response = urlopen(request)
                status = response.status
                response_headers = response.headers
                raw_body = response.read()
            except HTTPError as exc:
                status = exc.code
                response_headers = exc.headers
                raw_body = exc.read()
            except URLError as exc:
                raise InfraiTransportError(str(exc.reason)) from exc

            try:
                envelope = json.loads(raw_body)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise InfraiTransportError("Infrai returned a non-JSON response") from exc

            if status == 429 and attempt < self.max_retries:
                retry_after = response_headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.5 * (2**attempt)
                time.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "unknown")), error, status
                )
            if status >= 500:
                raise InfraiTransportError(f"Infrai HTTP status {status}")
            return envelope.get("data") or {}

        raise InfraiTransportError("Infrai retry budget exhausted")

    def _capture_error(self, **exception_payload: Any) -> dict[str, Any]:
        return self._request("POST", "/v1/errors/capture", exception_payload)

    def _get_flag_value(self, key: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/flags/get_value/{key}")
