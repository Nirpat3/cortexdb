"""
CortexDB Python Client
pip install cortexdb-client

Usage:
    from cortexdb_client import CortexDBClient

    client = CortexDBClient("http://localhost:5400")
    result = client.query("SELECT * FROM users WHERE age > 30")

    # With context manager
    with CortexDBClient("http://localhost:5400", api_key="sk-...") as client:
        rows = client.query("SELECT name, email FROM agents")

    # SuperAdmin operations
    admin = SuperAdminClient("http://localhost:5400")
    admin.login("my-passphrase")
    agents = admin.list_agents()
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

__all__ = [
    "CortexDBClient",
    "SuperAdminClient",
    "CortexDBError",
    "QueryResult",
]

__version__ = "0.9.0"

logger = logging.getLogger("cortexdb_client")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class CortexDBError(Exception):
    """Base exception for all CortexDB client errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    def __repr__(self) -> str:
        parts = [f"CortexDBError({self.args[0]!r}"]
        if self.status_code is not None:
            parts.append(f", status_code={self.status_code}")
        parts.append(")")
        return "".join(parts)


class ConnectionError(CortexDBError):
    """Raised when the client cannot reach CortexDB."""


class AuthenticationError(CortexDBError):
    """Raised on 401 / 403 responses."""


class QueryError(CortexDBError):
    """Raised when a query or write operation fails server-side."""


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

class QueryResult:
    """Thin wrapper around a CortexDB query response."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    @property
    def rows(self) -> list[dict[str, Any]]:
        """Return the result rows."""
        return self._raw.get("rows", self._raw.get("data", []))

    @property
    def row_count(self) -> int:
        return self._raw.get("rowCount", len(self.rows))

    @property
    def columns(self) -> list[str]:
        fields = self._raw.get("fields", [])
        if fields and isinstance(fields[0], dict):
            return [f.get("name", "") for f in fields]
        return list(fields)

    @property
    def raw(self) -> dict[str, Any]:
        """Access the unprocessed response payload."""
        return self._raw

    def __len__(self) -> int:
        return self.row_count

    def __iter__(self):
        return iter(self.rows)

    def __repr__(self) -> str:
        return f"QueryResult(row_count={self.row_count})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_headers(
    api_key: Optional[str] = None,
    token: Optional[str] = None,
) -> dict[str, str]:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["X-API-Key"] = api_key
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _handle_response(resp: httpx.Response) -> dict[str, Any]:
    """Raise appropriate errors for non-2xx responses."""
    if resp.status_code in (401, 403):
        raise AuthenticationError(
            f"Authentication failed ({resp.status_code})",
            status_code=resp.status_code,
            response_body=_safe_json(resp),
        )
    if resp.status_code >= 400:
        body = _safe_json(resp)
        msg = body.get("error", body.get("message", resp.text)) if isinstance(body, dict) else resp.text
        raise QueryError(
            f"Request failed ({resp.status_code}): {msg}",
            status_code=resp.status_code,
            response_body=body,
        )
    return _safe_json(resp)


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"text": resp.text}


# ---------------------------------------------------------------------------
# CortexDBClient
# ---------------------------------------------------------------------------

class CortexDBClient:
    """
    Lightweight client for CortexDB query and write operations.

    Parameters
    ----------
    base_url : str
        Root URL of the CortexDB instance (e.g. ``http://localhost:5400``).
    api_key : str, optional
        API key sent via ``X-API-Key`` header.
    timeout : float
        Request timeout in seconds (default 30).
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=_build_headers(api_key=api_key),
            timeout=httpx.Timeout(timeout),
        )
        logger.debug("CortexDBClient initialised for %s", self.base_url)

    # -- Context manager ----------------------------------------------------

    def __enter__(self) -> "CortexDBClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()
        logger.debug("CortexDBClient closed")

    # -- Core operations ----------------------------------------------------

    def query(
        self,
        cortexql: str,
        params: Optional[dict[str, Any] | list[Any]] = None,
    ) -> QueryResult:
        """
        Execute a read query against CortexDB.

        Parameters
        ----------
        cortexql : str
            The CortexQL / SQL statement.
        params : dict or list, optional
            Bind parameters for the query.

        Returns
        -------
        QueryResult
        """
        payload: dict[str, Any] = {"cortexql": cortexql}
        if params is not None:
            payload["params"] = params

        try:
            resp = self._client.post("/v1/query", json=payload)
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot connect to {self.base_url}: {exc}") from exc

        data = _handle_response(resp)
        return QueryResult(data)

    def write(
        self,
        cortexql: str,
        params: Optional[dict[str, Any] | list[Any]] = None,
    ) -> QueryResult:
        """
        Execute a write operation (INSERT / UPDATE / DELETE) against CortexDB.

        Parameters
        ----------
        cortexql : str
            The CortexQL / SQL statement.
        params : dict or list, optional
            Bind parameters.

        Returns
        -------
        QueryResult
        """
        payload: dict[str, Any] = {"cortexql": cortexql}
        if params is not None:
            payload["params"] = params

        try:
            resp = self._client.post("/v1/write", json=payload)
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot connect to {self.base_url}: {exc}") from exc

        data = _handle_response(resp)
        return QueryResult(data)

    # -- Health -------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """
        Check basic readiness of CortexDB.

        Returns
        -------
        dict
            Health payload from ``GET /health/ready``.
        """
        try:
            resp = self._client.get("/health/ready")
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot connect to {self.base_url}: {exc}") from exc
        return _handle_response(resp)

    def deep_health(self) -> dict[str, Any]:
        """
        Run a deep health check that verifies all internal engines.

        Returns
        -------
        dict
            Deep health payload from ``GET /health/deep``.
        """
        try:
            resp = self._client.get("/health/deep")
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot connect to {self.base_url}: {exc}") from exc
        return _handle_response(resp)

    def __repr__(self) -> str:
        return f"CortexDBClient(base_url={self.base_url!r})"


# ---------------------------------------------------------------------------
# SuperAdminClient
# ---------------------------------------------------------------------------

class SuperAdminClient:
    """
    Client for CortexDB SuperAdmin / management operations.

    Wraps the gateway API that sits in front of the agent-service,
    providing agent management, task control, chat, and marketplace access.

    Parameters
    ----------
    base_url : str
        Root URL of the CortexDB gateway (e.g. ``http://localhost:5400``).
    api_key : str, optional
        API key sent via ``X-API-Key`` header.
    timeout : float
        Request timeout in seconds (default 30).
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._token: Optional[str] = None
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=_build_headers(api_key=api_key),
            timeout=httpx.Timeout(timeout),
        )
        logger.debug("SuperAdminClient initialised for %s", self.base_url)

    # -- Context manager ----------------------------------------------------

    def __enter__(self) -> "SuperAdminClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    # -- Internal helpers ---------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return _build_headers(api_key=self.api_key, token=self._token)

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        try:
            resp = self._client.get(path, headers=self._headers(), params=params)
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot connect to {self.base_url}: {exc}") from exc
        return _handle_response(resp)

    def _post(self, path: str, json: Optional[dict[str, Any]] = None) -> Any:
        try:
            resp = self._client.post(path, headers=self._headers(), json=json or {})
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot connect to {self.base_url}: {exc}") from exc
        return _handle_response(resp)

    def _put(self, path: str, json: Optional[dict[str, Any]] = None) -> Any:
        try:
            resp = self._client.put(path, headers=self._headers(), json=json or {})
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot connect to {self.base_url}: {exc}") from exc
        return _handle_response(resp)

    # -- Authentication -----------------------------------------------------

    def login(self, passphrase: str) -> dict[str, Any]:
        """
        Authenticate with the superadmin passphrase.

        The returned JWT token is stored internally and sent with
        subsequent requests.

        Parameters
        ----------
        passphrase : str
            The superadmin passphrase.

        Returns
        -------
        dict
            Login response containing the token.
        """
        data = self._post("/api/v1/auth/login", json={"passphrase": passphrase})
        token = data.get("token") or data.get("access_token")
        if token:
            self._token = token
            logger.info("Authenticated with CortexDB superadmin")
        else:
            raise AuthenticationError("Login response did not contain a token", response_body=data)
        return data

    @property
    def is_authenticated(self) -> bool:
        """Return ``True`` if a token has been obtained via :meth:`login`."""
        return self._token is not None

    # -- Agents -------------------------------------------------------------

    def list_agents(self, **filters: Any) -> list[dict[str, Any]]:
        """
        List all agents, optionally filtered.

        Parameters
        ----------
        **filters
            Query-string filters (e.g. ``department="operations"``, ``tier=1``).

        Returns
        -------
        list[dict]
        """
        data = self._get("/api/v1/agents", params=filters or None)
        if isinstance(data, list):
            return data
        return data.get("agents", data.get("data", []))

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        """
        Get a single agent by ID.

        Parameters
        ----------
        agent_id : str
            Agent identifier (e.g. ``T1-OPS-POS-001``).

        Returns
        -------
        dict
        """
        return self._get(f"/api/v1/agents/{agent_id}")

    # -- Tasks --------------------------------------------------------------

    def create_task(
        self,
        agent_id: str,
        instruction: str,
        *,
        priority: int = 5,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Create and assign a task to an agent.

        Parameters
        ----------
        agent_id : str
            Target agent ID.
        instruction : str
            Natural-language task description.
        priority : int
            Priority level 1-10 (default 5).
        metadata : dict, optional
            Arbitrary metadata to attach to the task.

        Returns
        -------
        dict
            The created task record.
        """
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "instruction": instruction,
            "priority": priority,
        }
        if metadata:
            payload["metadata"] = metadata
        return self._post("/api/v1/tasks", json=payload)

    def list_tasks(self, **filters: Any) -> list[dict[str, Any]]:
        """
        List tasks, optionally filtered.

        Returns
        -------
        list[dict]
        """
        data = self._get("/api/v1/tasks", params=filters or None)
        if isinstance(data, list):
            return data
        return data.get("tasks", data.get("data", []))

    # -- Chat ---------------------------------------------------------------

    def chat(self, agent_id: str, message: str) -> dict[str, Any]:
        """
        Send a chat message to an agent and receive a response.

        Parameters
        ----------
        agent_id : str
            The agent to chat with.
        message : str
            The user message.

        Returns
        -------
        dict
            Chat response payload.
        """
        return self._post(
            "/api/v1/agents/chat",
            json={"agent_id": agent_id, "message": message},
        )

    # -- Marketplace --------------------------------------------------------

    def marketplace_list(self) -> list[dict[str, Any]]:
        """
        List all marketplace templates / integrations.

        Returns
        -------
        list[dict]
        """
        data = self._get("/api/v1/marketplace")
        if isinstance(data, list):
            return data
        return data.get("items", data.get("templates", data.get("data", [])))

    def marketplace_enable(self, item_id: str) -> dict[str, Any]:
        """
        Enable / activate a marketplace item.

        Parameters
        ----------
        item_id : str
            Marketplace item identifier.

        Returns
        -------
        dict
        """
        return self._post(f"/api/v1/marketplace/{item_id}/enable")

    def marketplace_disable(self, item_id: str) -> dict[str, Any]:
        """
        Disable / deactivate a marketplace item.

        Parameters
        ----------
        item_id : str
            Marketplace item identifier.

        Returns
        -------
        dict
        """
        return self._post(f"/api/v1/marketplace/{item_id}/disable")

    def __repr__(self) -> str:
        auth = "authenticated" if self.is_authenticated else "unauthenticated"
        return f"SuperAdminClient(base_url={self.base_url!r}, {auth})"
