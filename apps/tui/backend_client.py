"""Small HTTP client used by the terminal UI.

The TUI remains a client of the FastAPI adapter, just like the GUI.  This
module intentionally keeps the dependency surface tiny and avoids embedding any
business logic in the terminal layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class BackendClientError(RuntimeError):
    """Raised when the TUI cannot reach or parse the backend response."""


@dataclass(slots=True)
class AStockBackendClient:
    """HTTP wrapper around the shared FastAPI backend contract."""

    base_url: str = "http://127.0.0.1:18080"
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        return self._request("GET", path, params=params or None)

    def post(self, path: str, payload: dict[str, Any] | None = None, **params: Any) -> dict[str, Any]:
        return self._request("POST", path, json=payload or {}, params=params or None)

    def health(self) -> dict[str, Any]:
        return self.get("/api/health")

    def config(self) -> dict[str, Any]:
        return self.get("/api/config")

    def save_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return self.post("/api/config", {"config": config})

    def test_llm(self, config: dict[str, Any] | None = None, *, run_bench: bool = False) -> dict[str, Any]:
        return self.post("/api/config/test-llm", {"config": config or {}, "run_bench": run_bench})

    def list_models(self) -> dict[str, Any]:
        return self.post("/api/bench", {"list_models": True})

    def start_auto_investment(
        self,
        *,
        models: list[str] | None = None,
        offline: bool = False,
        max_count: int | None = None,
        days: int | None = None,
        background: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "models": models,
            "offline": offline,
            "max_count": max_count,
            "days": days,
        }
        endpoint = "/api/auto-investment/background" if background else "/api/auto-investment"
        return self.post(endpoint, payload)

    def run_status(self) -> dict[str, Any]:
        return self.get("/api/runs/current")

    def decisions(self) -> dict[str, Any]:
        return self.get("/api/decisions")

    def stock_board(self) -> dict[str, Any]:
        return self.get("/api/stocks/board")

    def rankings(self) -> dict[str, Any]:
        return self.get("/api/metrics/rankings")

    def data_providers(self) -> dict[str, Any]:
        return self.get("/api/data/providers")

    def agent_flow(self) -> dict[str, Any]:
        return self.get("/api/agents/flow")

    def learning_status(self) -> dict[str, Any]:
        return self.get("/api/agents/learning/status")

    def learning_suggestions(self) -> dict[str, Any]:
        return self.get("/api/agents/learning/suggestions")

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        try:
            response = requests.request(method, url, timeout=self.timeout_seconds, **kwargs)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise BackendClientError(f"Backend request failed: {method} {url}: {exc}") from exc
        except ValueError as exc:
            raise BackendClientError(f"Backend returned non-JSON response: {method} {url}") from exc
        if not isinstance(payload, dict):
            raise BackendClientError(f"Backend returned unexpected JSON shape: {method} {url}")
        return payload
