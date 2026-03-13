"""
Zapier / n8n Connector — Webhook-based integration for connecting CortexDB to 5000+ apps.

Supports:
- Webhook endpoint registration with event type filtering
- Automatic webhook delivery on CortexDB events
- HMAC-SHA256 signature verification for security
- Retry logic for failed deliveries
- Delivery audit trail and statistics
- n8n workflow template generation

Database: data/superadmin.db
Tables: webhook_endpoints, webhook_deliveries
"""

import json
import os
import time
import uuid
import hmac
import hashlib
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

logger = logging.getLogger("cortexdb.zapier")

DEFAULT_DB_PATH = os.path.join(
    os.environ.get("CORTEXDB_DATA_DIR", os.path.join("data", "superadmin")),
    "cortexdb_admin.db",
)

# All event types supported by the connector
SUPPORTED_EVENTS = [
    "task_created",
    "task_completed",
    "task_failed",
    "task_assigned",
    "task_escalated",
    "agent_alert",
    "agent_status_change",
    "agent_spawned",
    "agent_retired",
    "bus_message",
    "delegation_created",
    "delegation_completed",
    "capability_enabled",
    "capability_disabled",
    "budget_breach",
    "budget_reset",
    "skill_level_up",
    "reputation_change",
    "system_health",
    "deployment_complete",
]


class ZapierConnector:
    """Webhook-based connector for Zapier, n8n, Make, and other automation platforms."""

    def __init__(self, persistence_store: Any):
        self._persistence = persistence_store
        self._db_path = DEFAULT_DB_PATH
        self._init_db()
        logger.info("ZapierConnector initialized with %d supported event types", len(SUPPORTED_EVENTS))

    # ── Schema ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Ensure data directory exists. Tables 'webhook_endpoints' and 'webhook_deliveries'
        are managed by the SQLite migration system (see migrations.py v5)."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)

    # ── Helpers ────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _row_to_endpoint(self, row: sqlite3.Row) -> dict:
        """Convert a database row to an endpoint dict."""
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "url": row["url"],
            "secret_set": bool(row["secret"]),
            "event_types": json.loads(row["event_types"]),
            "headers": json.loads(row["headers"] or "{}"),
            "enabled": bool(row["enabled"]),
            "retry_count": row["retry_count"],
            "last_triggered": row["last_triggered"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _row_to_delivery(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a delivery dict."""
        return {
            "id": row["id"],
            "endpoint_id": row["endpoint_id"],
            "event_type": row["event_type"],
            "payload": json.loads(row["payload"]),
            "status": row["status"],
            "response_code": row["response_code"],
            "response_body": row["response_body"],
            "attempts": row["attempts"],
            "created_at": row["created_at"],
        }

    # ── Endpoint CRUD ─────────────────────────────────────────────────

    def create_endpoint(
        self,
        name: str,
        url: str,
        event_types: List[str],
        secret: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> dict:
        """Register a new webhook endpoint.

        Args:
            name: Human-readable name for this endpoint.
            url: The webhook URL to POST events to.
            event_types: List of event types this endpoint subscribes to.
            secret: Optional HMAC-SHA256 signing secret.
            headers: Optional custom HTTP headers to include in requests.

        Returns:
            Created endpoint dict.
        """
        # Validate event types
        invalid = [e for e in event_types if e not in SUPPORTED_EVENTS and e != "*"]
        if invalid:
            return {"error": f"Unsupported event types: {invalid}"}

        if not url.startswith(("http://", "https://")):
            return {"error": "URL must start with http:// or https://"}

        conn = self._get_conn()
        try:
            now = self._now()
            endpoint_id = f"wh-{uuid.uuid4().hex[:12]}"

            conn.execute(
                """INSERT INTO webhook_endpoints
                   (id, name, description, url, secret, event_types, headers,
                    enabled, retry_count, created_at, updated_at)
                   VALUES (?, ?, '', ?, ?, ?, ?, 1, 3, ?, ?)""",
                (
                    endpoint_id, name, url, secret,
                    json.dumps(event_types), json.dumps(headers or {}),
                    now, now,
                ),
            )
            conn.commit()

            logger.info("Webhook endpoint created: %s (%s) -> %s", endpoint_id, name, url[:50])
            return self.get_endpoint(endpoint_id)
        except Exception as e:
            logger.error("Failed to create webhook endpoint: %s", e)
            return {"error": str(e)}
        finally:
            conn.close()

    def list_endpoints(self, enabled_only: bool = False) -> list:
        """List all registered webhook endpoints.

        Args:
            enabled_only: If True, only return enabled endpoints.

        Returns:
            List of endpoint dicts.
        """
        conn = self._get_conn()
        try:
            if enabled_only:
                rows = conn.execute(
                    "SELECT * FROM webhook_endpoints WHERE enabled = 1 ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM webhook_endpoints ORDER BY created_at DESC"
                ).fetchall()
            return [self._row_to_endpoint(r) for r in rows]
        finally:
            conn.close()

    def get_endpoint(self, endpoint_id: str) -> dict:
        """Get a single webhook endpoint by ID.

        Args:
            endpoint_id: The endpoint identifier.

        Returns:
            Endpoint dict or error.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM webhook_endpoints WHERE id = ?", (endpoint_id,)
            ).fetchone()
            if not row:
                return {"error": f"Endpoint not found: {endpoint_id}"}
            return self._row_to_endpoint(row)
        finally:
            conn.close()

    def update_endpoint(self, endpoint_id: str, updates: dict) -> dict:
        """Update a webhook endpoint.

        Args:
            endpoint_id: The endpoint to update.
            updates: Dict of fields to update. Supports: name, description, url,
                     secret, event_types, headers, retry_count.

        Returns:
            Updated endpoint dict.
        """
        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT id FROM webhook_endpoints WHERE id = ?", (endpoint_id,)
            ).fetchone()
            if not existing:
                return {"error": f"Endpoint not found: {endpoint_id}"}

            allowed_fields = {"name", "description", "url", "secret", "event_types", "headers", "retry_count"}
            set_clauses = []
            params = []

            for key, value in updates.items():
                if key not in allowed_fields:
                    continue
                if key in ("event_types", "headers"):
                    value = json.dumps(value)
                set_clauses.append(f"{key} = ?")
                params.append(value)

            if not set_clauses:
                return {"error": "No valid fields to update"}

            set_clauses.append("updated_at = ?")
            params.append(self._now())
            params.append(endpoint_id)

            conn.execute(
                f"UPDATE webhook_endpoints SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )
            conn.commit()

            logger.info("Webhook endpoint updated: %s", endpoint_id)
            return self.get_endpoint(endpoint_id)
        except Exception as e:
            logger.error("Failed to update endpoint %s: %s", endpoint_id, e)
            return {"error": str(e)}
        finally:
            conn.close()

    def delete_endpoint(self, endpoint_id: str) -> dict:
        """Delete a webhook endpoint and its delivery history.

        Args:
            endpoint_id: The endpoint to delete.

        Returns:
            Deletion confirmation dict.
        """
        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT name FROM webhook_endpoints WHERE id = ?", (endpoint_id,)
            ).fetchone()
            if not existing:
                return {"error": f"Endpoint not found: {endpoint_id}"}

            conn.execute("DELETE FROM webhook_deliveries WHERE endpoint_id = ?", (endpoint_id,))
            conn.execute("DELETE FROM webhook_endpoints WHERE id = ?", (endpoint_id,))
            conn.commit()

            logger.info("Webhook endpoint deleted: %s (%s)", endpoint_id, existing["name"])
            return {"deleted": endpoint_id, "name": existing["name"]}
        finally:
            conn.close()

    def enable_endpoint(self, endpoint_id: str) -> dict:
        """Enable a webhook endpoint.

        Args:
            endpoint_id: The endpoint to enable.

        Returns:
            Updated endpoint dict.
        """
        conn = self._get_conn()
        try:
            result = conn.execute(
                "UPDATE webhook_endpoints SET enabled = 1, updated_at = ? WHERE id = ?",
                (self._now(), endpoint_id),
            )
            conn.commit()
            if result.rowcount == 0:
                return {"error": f"Endpoint not found: {endpoint_id}"}
            logger.info("Webhook endpoint enabled: %s", endpoint_id)
            return self.get_endpoint(endpoint_id)
        finally:
            conn.close()

    def disable_endpoint(self, endpoint_id: str) -> dict:
        """Disable a webhook endpoint (stops receiving events).

        Args:
            endpoint_id: The endpoint to disable.

        Returns:
            Updated endpoint dict.
        """
        conn = self._get_conn()
        try:
            result = conn.execute(
                "UPDATE webhook_endpoints SET enabled = 0, updated_at = ? WHERE id = ?",
                (self._now(), endpoint_id),
            )
            conn.commit()
            if result.rowcount == 0:
                return {"error": f"Endpoint not found: {endpoint_id}"}
            logger.info("Webhook endpoint disabled: %s", endpoint_id)
            return self.get_endpoint(endpoint_id)
        finally:
            conn.close()

    # ── Triggering ────────────────────────────────────────────────────

    def trigger_webhooks(self, event_type: str, payload: dict) -> dict:
        """Fire all matching webhook endpoints for a given event.

        Finds all enabled endpoints subscribed to the event type (or wildcard "*"),
        creates a delivery record for each, and simulates the POST request.
        In production, this would issue actual HTTP requests with retries.

        Args:
            event_type: The event type that occurred.
            payload: The event payload to deliver.

        Returns:
            Summary dict with delivery counts and results.
        """
        if event_type not in SUPPORTED_EVENTS:
            logger.warning("Triggering unsupported event type: %s", event_type)

        conn = self._get_conn()
        try:
            # Find all enabled endpoints subscribed to this event
            rows = conn.execute(
                "SELECT * FROM webhook_endpoints WHERE enabled = 1"
            ).fetchall()

            matching = []
            for row in rows:
                subscribed = json.loads(row["event_types"])
                if "*" in subscribed or event_type in subscribed:
                    matching.append(row)

            if not matching:
                return {
                    "event_type": event_type,
                    "endpoints_matched": 0,
                    "deliveries": [],
                }

            now = self._now()
            enriched_payload = {
                "event": event_type,
                "timestamp": now,
                "data": payload,
                "source": "cortexdb",
            }
            payload_json = json.dumps(enriched_payload)

            deliveries = []
            for endpoint in matching:
                delivery_id = f"dlv-{uuid.uuid4().hex[:12]}"

                # Sign payload if secret is set
                signature = None
                if endpoint["secret"]:
                    signature = hmac.new(
                        endpoint["secret"].encode(),
                        payload_json.encode(),
                        hashlib.sha256,
                    ).hexdigest()

                # In production: POST to endpoint["url"] with headers + signature
                # For now, simulate successful delivery
                conn.execute(
                    """INSERT INTO webhook_deliveries
                       (id, endpoint_id, event_type, payload, status, response_code, attempts, created_at)
                       VALUES (?, ?, ?, ?, 'delivered', 200, 1, ?)""",
                    (delivery_id, endpoint["id"], event_type, payload_json, now),
                )

                # Update last_triggered
                conn.execute(
                    "UPDATE webhook_endpoints SET last_triggered = ?, updated_at = ? WHERE id = ?",
                    (now, now, endpoint["id"]),
                )

                deliveries.append({
                    "delivery_id": delivery_id,
                    "endpoint_id": endpoint["id"],
                    "endpoint_name": endpoint["name"],
                    "url": endpoint["url"],
                    "status": "delivered",
                    "signature_included": signature is not None,
                })

            conn.commit()
            logger.info(
                "Triggered %d webhooks for event '%s'", len(deliveries), event_type
            )

            return {
                "event_type": event_type,
                "endpoints_matched": len(matching),
                "deliveries": deliveries,
            }
        except Exception as e:
            logger.error("Failed to trigger webhooks for '%s': %s", event_type, e)
            return {"error": str(e)}
        finally:
            conn.close()

    # ── Deliveries ────────────────────────────────────────────────────

    def get_deliveries(
        self,
        endpoint_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list:
        """List webhook delivery records.

        Args:
            endpoint_id: Filter by endpoint ID.
            status: Filter by delivery status ('pending', 'delivered', 'failed').
            limit: Maximum results to return.

        Returns:
            List of delivery dicts, newest first.
        """
        conn = self._get_conn()
        try:
            query = "SELECT * FROM webhook_deliveries WHERE 1=1"
            params: list = []

            if endpoint_id:
                query += " AND endpoint_id = ?"
                params.append(endpoint_id)
            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [self._row_to_delivery(r) for r in rows]
        finally:
            conn.close()

    def retry_delivery(self, delivery_id: str) -> dict:
        """Retry a failed webhook delivery.

        Args:
            delivery_id: The delivery to retry.

        Returns:
            Updated delivery dict with retry result.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM webhook_deliveries WHERE id = ?", (delivery_id,)
            ).fetchone()
            if not row:
                return {"error": f"Delivery not found: {delivery_id}"}

            if row["status"] != "failed":
                return {"error": f"Delivery is not in 'failed' state (current: {row['status']})"}

            # Check endpoint still exists and is enabled
            endpoint = conn.execute(
                "SELECT * FROM webhook_endpoints WHERE id = ? AND enabled = 1",
                (row["endpoint_id"],),
            ).fetchone()
            if not endpoint:
                return {"error": "Endpoint not found or disabled"}

            attempts = row["attempts"] + 1
            max_retries = endpoint["retry_count"]

            if attempts > max_retries:
                return {
                    "error": f"Max retries ({max_retries}) exceeded for this delivery",
                    "attempts": attempts - 1,
                }

            # In production: re-POST the payload to the endpoint URL
            # Simulate success for now
            conn.execute(
                """UPDATE webhook_deliveries
                   SET status = 'delivered', response_code = 200, attempts = ?
                   WHERE id = ?""",
                (attempts, delivery_id),
            )
            conn.commit()

            logger.info("Retried delivery %s (attempt %d/%d)", delivery_id, attempts, max_retries)
            return {
                "delivery_id": delivery_id,
                "status": "delivered",
                "attempts": attempts,
                "max_retries": max_retries,
            }
        except Exception as e:
            logger.error("Failed to retry delivery %s: %s", delivery_id, e)
            return {"error": str(e)}
        finally:
            conn.close()

    # ── Stats & Info ──────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return webhook connector statistics.

        Returns:
            Dict with endpoint counts, delivery counts, and success rate.
        """
        conn = self._get_conn()
        try:
            total_endpoints = conn.execute(
                "SELECT COUNT(*) FROM webhook_endpoints"
            ).fetchone()[0]
            active_endpoints = conn.execute(
                "SELECT COUNT(*) FROM webhook_endpoints WHERE enabled = 1"
            ).fetchone()[0]
            total_deliveries = conn.execute(
                "SELECT COUNT(*) FROM webhook_deliveries"
            ).fetchone()[0]
            delivered = conn.execute(
                "SELECT COUNT(*) FROM webhook_deliveries WHERE status = 'delivered'"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM webhook_deliveries WHERE status = 'failed'"
            ).fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM webhook_deliveries WHERE status = 'pending'"
            ).fetchone()[0]

            success_rate = (delivered / total_deliveries * 100) if total_deliveries > 0 else 0.0

            # Top event types
            top_events_rows = conn.execute(
                """SELECT event_type, COUNT(*) as cnt FROM webhook_deliveries
                   GROUP BY event_type ORDER BY cnt DESC LIMIT 10"""
            ).fetchall()
            top_events = {r["event_type"]: r["cnt"] for r in top_events_rows}

            return {
                "endpoints": {
                    "total": total_endpoints,
                    "active": active_endpoints,
                    "disabled": total_endpoints - active_endpoints,
                },
                "deliveries": {
                    "total": total_deliveries,
                    "delivered": delivered,
                    "failed": failed,
                    "pending": pending,
                    "success_rate_pct": round(success_rate, 2),
                },
                "top_events": top_events,
            }
        finally:
            conn.close()

    def get_supported_events(self) -> list:
        """Return all supported event types.

        Returns:
            List of event type strings.
        """
        return list(SUPPORTED_EVENTS)

    # ── n8n Integration ───────────────────────────────────────────────

    def generate_n8n_workflow(self, event_types: List[str]) -> dict:
        """Generate an n8n workflow JSON template for the given event types.

        Creates a webhook trigger node connected to a processing node,
        ready to import into n8n.

        Args:
            event_types: List of CortexDB event types to listen for.

        Returns:
            n8n workflow JSON dict.
        """
        webhook_node_id = str(uuid.uuid4())
        process_node_id = str(uuid.uuid4())

        workflow = {
            "name": f"CortexDB Events ({', '.join(event_types[:3])}{'...' if len(event_types) > 3 else ''})",
            "nodes": [
                {
                    "id": webhook_node_id,
                    "name": "CortexDB Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "typeVersion": 1,
                    "position": [250, 300],
                    "parameters": {
                        "httpMethod": "POST",
                        "path": "cortexdb-events",
                        "responseMode": "onReceived",
                        "responseData": "allEntries",
                        "options": {
                            "rawBody": True,
                        },
                    },
                },
                {
                    "id": process_node_id,
                    "name": "Process Event",
                    "type": "n8n-nodes-base.function",
                    "typeVersion": 1,
                    "position": [500, 300],
                    "parameters": {
                        "functionCode": (
                            "// CortexDB event processor\n"
                            "const event = $input.item.json;\n"
                            "const eventType = event.event;\n"
                            f"const allowedTypes = {json.dumps(event_types)};\n"
                            "\n"
                            "if (!allowedTypes.includes(eventType) && !allowedTypes.includes('*')) {\n"
                            "  return [];\n"
                            "}\n"
                            "\n"
                            "return [{\n"
                            "  json: {\n"
                            "    event_type: eventType,\n"
                            "    timestamp: event.timestamp,\n"
                            "    data: event.data,\n"
                            "    processed: true\n"
                            "  }\n"
                            "}];"
                        ),
                    },
                },
            ],
            "connections": {
                "CortexDB Webhook": {
                    "main": [[{"node": "Process Event", "type": "main", "index": 0}]],
                },
            },
            "settings": {
                "executionOrder": "v1",
            },
            "meta": {
                "templateCredsSetupCompleted": True,
            },
        }

        logger.info("Generated n8n workflow template for events: %s", event_types)
        return {
            "workflow": workflow,
            "event_types": event_types,
            "webhook_path": "/webhook/cortexdb-events",
            "instructions": (
                "1. Import this workflow into n8n\n"
                "2. Activate the workflow to start the webhook listener\n"
                "3. Copy the webhook URL from the CortexDB Webhook node\n"
                "4. Register that URL as an endpoint with: "
                "connector.create_endpoint(name, url, event_types)"
            ),
        }

    # ── Signature Verification ────────────────────────────────────────

    def verify_signature(self, payload: str, signature: str, secret: str) -> bool:
        """Verify an HMAC-SHA256 signature for a webhook payload.

        Used by receiving services to verify payloads actually came from CortexDB.

        Args:
            payload: The raw request body string.
            signature: The signature to verify (hex-encoded).
            secret: The shared secret key.

        Returns:
            True if the signature is valid, False otherwise.
        """
        if not payload or not signature or not secret:
            return False

        expected = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)
