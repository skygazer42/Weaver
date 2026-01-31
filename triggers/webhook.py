"""
Webhook Handler for Webhook Triggers.

Handles HTTP webhook requests and triggers agent execution.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .models import TriggerStatus, WebhookTrigger

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self):
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """
        Check if request is allowed.

        Args:
            key: Unique key (e.g., trigger_id)
            limit: Max requests allowed
            window: Time window in seconds

        Returns:
            True if allowed, False if rate limited
        """
        now = time.time()
        requests = self.requests[key]

        # Remove old requests outside window
        self.requests[key] = [t for t in requests if now - t < window]

        # Check limit
        if len(self.requests[key]) >= limit:
            return False

        # Record this request
        self.requests[key].append(now)
        return True


class WebhookHandler:
    """
    Handler for webhook triggers.

    Provides methods for registering webhooks and processing incoming requests.
    """

    def __init__(self):
        self.triggers: Dict[str, WebhookTrigger] = {}
        self.callbacks: Dict[str, Callable] = {}
        self.rate_limiter = RateLimiter()

    def add_trigger(
        self,
        trigger: WebhookTrigger,
        callback: Callable[[WebhookTrigger, Dict[str, Any]], Any],
    ) -> str:
        """
        Add a webhook trigger.

        Args:
            trigger: The webhook trigger
            callback: Function to call when webhook is triggered

        Returns:
            The webhook endpoint path
        """
        # Generate endpoint path if not set
        if not trigger.endpoint_path:
            trigger.endpoint_path = f"/webhook/{trigger.id}"

        self.triggers[trigger.id] = trigger
        self.callbacks[trigger.id] = callback

        logger.info(
            f"[webhook] Registered webhook '{trigger.name}' "
            f"at {trigger.endpoint_path}"
        )

        return trigger.endpoint_path

    def remove_trigger(self, trigger_id: str) -> bool:
        """Remove a webhook trigger."""
        if trigger_id not in self.triggers:
            return False

        trigger = self.triggers[trigger_id]
        del self.triggers[trigger_id]
        if trigger_id in self.callbacks:
            del self.callbacks[trigger_id]

        logger.info(f"[webhook] Removed webhook: {trigger.name}")
        return True

    def get_trigger(self, trigger_id: str) -> Optional[WebhookTrigger]:
        """Get a trigger by ID."""
        return self.triggers.get(trigger_id)

    def get_trigger_by_path(self, path: str) -> Optional[WebhookTrigger]:
        """Get a trigger by endpoint path."""
        for trigger in self.triggers.values():
            if trigger.endpoint_path == path:
                return trigger
        return None

    def list_triggers(self) -> List[WebhookTrigger]:
        """List all webhook triggers."""
        return list(self.triggers.values())

    async def handle_request(
        self,
        trigger_id: str,
        method: str,
        body: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_header: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle an incoming webhook request.

        Args:
            trigger_id: The trigger ID
            method: HTTP method
            body: Request body (JSON)
            query_params: Query parameters
            headers: Request headers
            auth_header: Authorization header value

        Returns:
            Response dict with status and message
        """
        trigger = self.triggers.get(trigger_id)
        if not trigger:
            return {
                "success": False,
                "error": "Webhook not found",
                "status_code": 404,
            }

        # Check status
        if trigger.status != TriggerStatus.ACTIVE:
            return {
                "success": False,
                "error": f"Webhook is {trigger.status.value}",
                "status_code": 503,
            }

        # Check HTTP method
        if method.upper() not in [m.upper() for m in trigger.http_methods]:
            return {
                "success": False,
                "error": f"Method {method} not allowed",
                "status_code": 405,
            }

        # Check authentication
        if trigger.require_auth:
            if not self._validate_auth(trigger, auth_header):
                return {
                    "success": False,
                    "error": "Authentication failed",
                    "status_code": 401,
                }

        # Check rate limit
        if trigger.rate_limit:
            if not self.rate_limiter.is_allowed(
                trigger.id,
                trigger.rate_limit,
                trigger.rate_limit_window,
            ):
                return {
                    "success": False,
                    "error": "Rate limit exceeded",
                    "status_code": 429,
                }

        # Build execution params
        exec_params = {}

        if trigger.extract_body and body:
            exec_params["body"] = body

        if trigger.extract_query and query_params:
            exec_params["query"] = query_params

        if trigger.extract_headers and headers:
            exec_params["headers"] = {
                k: v for k, v in headers.items()
                if k.lower() in [h.lower() for h in trigger.extract_headers]
            }

        # Merge with task_params
        exec_params.update(trigger.task_params)

        # Execute callback
        callback = self.callbacks.get(trigger.id)
        if not callback:
            return {
                "success": False,
                "error": "No callback registered",
                "status_code": 500,
            }

        try:
            # Update trigger stats
            trigger.last_executed_at = datetime.now()
            trigger.execution_count += 1

            # Call the callback
            if asyncio.iscoroutinefunction(callback):
                result = await callback(trigger, exec_params)
            else:
                result = callback(trigger, exec_params)

            return {
                "success": True,
                "message": "Webhook triggered successfully",
                "trigger_id": trigger.id,
                "trigger_name": trigger.name,
                "execution_count": trigger.execution_count,
                "result": result,
                "status_code": 200,
            }

        except Exception as e:
            logger.error(f"[webhook] Error executing webhook '{trigger.name}': {e}")
            trigger.failure_count += 1

            return {
                "success": False,
                "error": str(e),
                "status_code": 500,
            }

    def _validate_auth(self, trigger: WebhookTrigger, auth_header: Optional[str]) -> bool:
        """Validate authentication for a webhook request."""
        if not auth_header:
            return False

        # Simple token validation
        if trigger.auth_token:
            # Support Bearer token or direct token
            token = auth_header
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:]

            return hmac.compare_digest(token, trigger.auth_token)

        return False

    def generate_auth_token(self) -> str:
        """Generate a secure authentication token."""
        import secrets
        return secrets.token_urlsafe(32)


# Global webhook handler instance
_webhook_handler: Optional[WebhookHandler] = None


def get_webhook_handler() -> WebhookHandler:
    """Get the global webhook handler instance."""
    global _webhook_handler
    if _webhook_handler is None:
        _webhook_handler = WebhookHandler()
    return _webhook_handler
