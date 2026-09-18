"""Shared Turso/libSQL client factory used by ingestion, execution, and seeding.

Uses Turso's documented HTTP `v2/pipeline` API directly via `requests`, rather than
the `libsql-client` package — that package's HTTP path raises a KeyError on Turso's
current response shape for non-SELECT (DDL/DML) statements, and its WebSocket path
fails the Hrana handshake against Turso's edge. A minimal direct client avoids both.
"""
import base64
from typing import Any, Optional

import requests

from config.settings import settings


def _http_url(url: str) -> str:
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    if url.startswith("wss://"):
        return "https://" + url[len("wss://"):]
    if url.startswith("ws://"):
        return "http://" + url[len("ws://"):]
    return url.rstrip("/")


def _encode_arg(value: Any) -> dict:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, (bytes, bytearray)):
        return {"type": "blob", "value": base64.b64encode(value).decode("ascii")}
    return {"type": "text", "value": str(value)}


def _decode_value(cell: dict) -> Any:
    cell_type = cell.get("type")
    value = cell.get("value")
    if cell_type == "null":
        return None
    if cell_type == "integer":
        return int(value)
    if cell_type == "float":
        return float(value)
    if cell_type == "blob":
        return base64.b64decode(value)
    return value  # text


class ResultSet:
    def __init__(self, columns: list[str], rows: list[list[Any]]):
        self.columns = columns
        self.rows = rows


class TursoClient:
    def __init__(self, url: str, auth_token: str):
        self.base_url = _http_url(url)
        self.auth_token = auth_token
        self._session = requests.Session()

    def execute(self, sql: str, args: Optional[list[Any]] = None) -> ResultSet:
        stmt: dict = {"sql": sql}
        if args:
            stmt["args"] = [_encode_arg(a) for a in args]

        response = self._session.post(
            f"{self.base_url}/v2/pipeline",
            json={"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]},
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        first = payload["results"][0]
        if first["type"] == "error":
            raise RuntimeError(first["error"].get("message", "Turso query failed"))

        result = first["response"]["result"]
        columns = [col["name"] for col in result.get("cols", [])]
        rows = [[_decode_value(cell) for cell in row] for row in result.get("rows", [])]
        return ResultSet(columns=columns, rows=rows)

    def close(self) -> None:
        self._session.close()


def get_client() -> TursoClient:
    return TursoClient(url=settings.turso_database_url, auth_token=settings.turso_auth_token)
