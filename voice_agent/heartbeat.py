"""Heartbeat thread for maintaining connection to the hub."""

import logging
import threading
from collections.abc import Callable

import httpx

from .constants import HUB_HEARTBEAT_INTERVAL, HUB_HEARTBEAT_TIMEOUT, HUB_REQUEST_TIMEOUT

logger = logging.getLogger("voice-agent")


class HeartbeatThread:
    """Manages periodic heartbeat requests to the hub in a background thread."""

    def __init__(self, hub_url: str, token_getter: Callable[[], str]):
        """Initialize heartbeat thread.

        Args:
            hub_url: Base URL of the hub
            token_getter: Callable that returns the current auth token (allows refreshing)
        """
        self.hub_url = hub_url
        self.token_getter = token_getter
        self.shutdown_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.failure_count = 0
        self.max_failures = 10  # Stop logging after this many consecutive failures

    def _loop(self) -> None:
        """Background thread loop that sends heartbeats."""
        while not self.shutdown_event.is_set():
            # Use wait() instead of sleep() so shutdown is responsive
            if self.shutdown_event.wait(timeout=HUB_HEARTBEAT_INTERVAL):
                break  # Shutdown requested

            try:
                token = self.token_getter()
                with httpx.Client(timeout=HUB_REQUEST_TIMEOUT) as client:
                    resp = client.post(
                        f"{self.hub_url}/agent/heartbeat",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=HUB_HEARTBEAT_TIMEOUT,
                    )
                    resp.raise_for_status()
                # Reset failure count on success
                if self.failure_count > 0:
                    logger.info("Heartbeat recovered after %d failures", self.failure_count)
                    self.failure_count = 0
            except Exception as exc:
                self.failure_count += 1
                if self.failure_count <= self.max_failures:
                    logger.warning("Heartbeat failed (#%d): %s", self.failure_count, exc)
                elif self.failure_count == self.max_failures + 1:
                    logger.error("Heartbeat failing repeatedly, suppressing further warnings")

    def start(self) -> None:
        """Start the heartbeat thread."""
        if self.thread is not None:
            logger.warning("Heartbeat thread already started")
            return
        self.thread = threading.Thread(target=self._loop, daemon=True, name="HeartbeatThread")
        self.thread.start()
        logger.info("Heartbeat thread started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the heartbeat thread gracefully.

        Args:
            timeout: Max seconds to wait for thread to stop
        """
        if self.thread is None:
            return
        logger.info("Stopping heartbeat thread...")
        self.shutdown_event.set()
        self.thread.join(timeout=timeout)
        if self.thread.is_alive():
            logger.warning("Heartbeat thread did not stop within %s seconds", timeout)
        else:
            logger.info("Heartbeat thread stopped")
        self.thread = None


def _start_heartbeat(hub_url: str, token: str) -> HeartbeatThread:
    """Start a daemon thread that sends heartbeats every HUB_HEARTBEAT_INTERVAL seconds.

    Returns the HeartbeatThread instance for shutdown control."""
    # Use a lambda to allow token to be updated if needed
    # (though in current implementation it's static)
    heartbeat = HeartbeatThread(hub_url, lambda: token)
    heartbeat.start()
    return heartbeat
