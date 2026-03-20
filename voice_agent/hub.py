"""Hub API client for agent authentication and registration."""

import contextlib
import logging
import os
import platform
import time

import httpx

from .constants import HUB_DEVICE_AUTH_POLL_INTERVAL, HUB_REQUEST_TIMEOUT, HubConfig
from .retry import exponential_backoff_with_jitter, retry_with_backoff

logger = logging.getLogger("voice-agent")

# Platform-specific file locking
_IS_WINDOWS = platform.system() == "Windows"
if not _IS_WINDOWS:
    import fcntl
else:
    import msvcrt


@contextlib.contextmanager
def _file_lock(file_obj):
    """Context manager for file locking (cross-platform).

    Args:
        file_obj: Open file object to lock

    Yields:
        The locked file object
    """
    try:
        if _IS_WINDOWS:
            # Windows: lock using msvcrt
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
        else:
            # Unix: lock using fcntl
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
        yield file_obj
    finally:
        if _IS_WINDOWS:
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        else:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


def _hub_authenticate(hub_url: str, base_name: str) -> str:
    """Return a valid hub token, prompting device auth if needed.
    Raises RuntimeError on network or server errors."""
    _here = os.path.dirname(os.path.abspath(__file__))
    token_file = os.path.join(_here, f".hub-token-{base_name}")

    if os.path.exists(token_file):
        try:
            with open(token_file, "r+") as f, _file_lock(f):
                token = f.read().strip()
                if token:
                    return token
        except OSError as exc:
            logger.warning("Failed to read token file, will re-authenticate: %s", exc)

    # Device-code flow
    try:
        with httpx.Client(timeout=HUB_REQUEST_TIMEOUT) as client:
            resp = client.post(f"{hub_url}/auth/device")
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as exc:
        raise RuntimeError(f"Failed to initiate device auth: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to parse device auth response: {exc}") from exc

    device_code = data["device_code"]
    verification_url = data["verification_url"]
    expires_in = data.get("expires_in", 300)

    print(f"[agent] Sign in to Talk to Claw: {verification_url}")
    print("[agent] Waiting for sign-in approval...")

    deadline = time.time() + expires_in
    poll_attempt = 0
    while time.time() < deadline:
        # Use exponential backoff with jitter to avoid thundering herd
        delay = exponential_backoff_with_jitter(
            poll_attempt,
            base_delay=HUB_DEVICE_AUTH_POLL_INTERVAL,
            max_delay=min(HUB_DEVICE_AUTH_POLL_INTERVAL * 4, 15.0),  # Cap at 15s
            jitter_factor=0.3,
        )
        time.sleep(delay)
        poll_attempt += 1

        try:
            with httpx.Client(timeout=HUB_REQUEST_TIMEOUT) as client:
                resp = client.get(f"{hub_url}/auth/device/token", params={"code": device_code})
                resp.raise_for_status()
                result = resp.json()
        except httpx.RequestError as exc:
            logger.warning("Device auth poll failed, will retry with backoff: %s", exc)
            continue
        except Exception as exc:
            logger.warning("Failed to parse device auth poll response, will retry: %s", exc)
            continue

        if "token" in result:
            token = result["token"]
            _here = os.path.dirname(os.path.abspath(__file__))
            token_path = os.path.join(_here, f".hub-token-{base_name}")
            # Use atomic write: write to temp file, then rename
            temp_path = f"{token_path}.tmp"
            with open(temp_path, "w") as f, _file_lock(f):
                f.write(token)
                f.flush()
                os.fsync(f.fileno())  # Ensure written to disk
            # Set secure permissions before making visible
            os.chmod(temp_path, 0o600)
            # Atomic rename (overwrites existing file)
            os.replace(temp_path, token_path)
            return token

        status = result.get("status", "")
        if status == "expired":
            print("[agent] Sign-in approval expired. Please restart the agent.")
            raise SystemExit(1)
        # status == "pending" — keep polling

    print("[agent] Timed out waiting for sign-in approval.")
    raise SystemExit(1)


def _hub_get_config(hub_url: str, token: str, base_name: str) -> HubConfig:
    """Fetch agent config from hub. Returns config dict.
    Raises ValueError if token is invalid (caller should re-auth).
    Raises RuntimeError for network or server errors."""
    _here = os.path.dirname(os.path.abspath(__file__))

    def _make_request() -> HubConfig:
        try:
            with httpx.Client(timeout=HUB_REQUEST_TIMEOUT) as client:
                resp = client.get(
                    f"{hub_url}/agent/config",
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Hub request timed out after {HUB_REQUEST_TIMEOUT}s: {hub_url}") from exc
        except httpx.ConnectError as exc:
            # Retryable: connection errors are often transient
            raise
        except httpx.RequestError as exc:
            raise RuntimeError(f"Hub request failed: {exc}") from exc

        if resp.status_code == 401:
            # Token expired — delete it so next call triggers re-auth
            token_file = os.path.join(_here, f".hub-token-{base_name}")
            if os.path.exists(token_file):
                try:
                    os.remove(token_file)
                except OSError as exc:
                    logger.warning("Failed to remove expired token file: %s", exc)
            raise ValueError("hub token invalid or expired")

        # Retry on 5xx server errors (transient)
        if 500 <= resp.status_code < 600:
            raise RuntimeError(f"Hub server error {resp.status_code}, retrying")

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Don't retry on 4xx client errors (except 401 handled above)
            raise RuntimeError(f"Hub returned error {resp.status_code}: {resp.text}") from exc

        try:
            return resp.json()
        except Exception as exc:
            raise RuntimeError(f"Failed to parse hub response as JSON: {resp.text[:200]}") from exc

    # Retry on connection errors and 5xx server errors
    try:
        return retry_with_backoff(
            _make_request,
            max_attempts=3,
            base_delay=1.0,
            max_delay=10.0,
            retryable_exceptions=(httpx.ConnectError, RuntimeError),
        )
    except ValueError:
        # Don't retry on auth errors
        raise


def _hub_register(
    hub_url: str, token: str, agent_name: str, display_name: str, config: HubConfig, base_name: str
) -> str:
    """Register agent with hub, persist agent_id, return call_url_base.
    Raises RuntimeError on network or server errors."""
    _here = os.path.dirname(os.path.abspath(__file__))

    def _make_request() -> str:
        try:
            with httpx.Client(timeout=HUB_REQUEST_TIMEOUT) as client:
                resp = client.post(
                    f"{hub_url}/agent/register",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "agent_name": agent_name,
                        "display_name": display_name,
                        "livekit_url": config.get("livekit_url", ""),
                        "livekit_api_key": config.get("livekit_api_key", ""),
                        "livekit_api_secret": config.get("livekit_api_secret", ""),
                        "deepgram_api_key": config.get("deepgram_api_key", ""),
                        "openai_api_key": config.get("openai_api_key", ""),
                    },
                )
        except httpx.ConnectError:
            # Retryable: connection errors are often transient
            raise
        except httpx.RequestError as exc:
            raise RuntimeError(f"Hub registration request failed: {exc}") from exc

        # Retry on 5xx server errors (transient)
        if 500 <= resp.status_code < 600:
            raise RuntimeError(f"Hub server error {resp.status_code}, retrying")

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Don't retry on 4xx client errors
            raise RuntimeError(f"Hub registration failed with status {resp.status_code}: {resp.text}") from exc

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Failed to parse hub registration response: {resp.text[:200]}") from exc

        if "agent_id" not in data or "call_url_base" not in data:
            raise RuntimeError(f"Hub registration response missing required fields: {data}")

        # Write agent ID atomically
        agent_id_file = os.path.join(_here, f".hub-agent-id-{base_name}")
        temp_path = f"{agent_id_file}.tmp"
        with open(temp_path, "w") as f, _file_lock(f):
            f.write(data["agent_id"])
            f.flush()
            os.fsync(f.fileno())
        # Set secure permissions before making visible
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, agent_id_file)

        return data["call_url_base"]

    # Retry on connection errors and 5xx server errors
    return retry_with_backoff(
        _make_request,
        max_attempts=3,
        base_delay=1.0,
        max_delay=10.0,
        retryable_exceptions=(httpx.ConnectError, RuntimeError),
    )
