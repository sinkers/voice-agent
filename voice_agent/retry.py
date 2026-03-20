"""Retry utilities with exponential backoff and jitter."""

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def exponential_backoff_with_jitter(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.3,
) -> float:
    """Calculate delay for exponential backoff with jitter.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter_factor: Amount of randomness to add (0.0-1.0)

    Returns:
        Delay in seconds with jitter applied

    Example:
        >>> # Attempt 0: ~1s, Attempt 1: ~2s, Attempt 2: ~4s, etc.
        >>> for i in range(5):
        ...     delay = exponential_backoff_with_jitter(i)
        ...     print(f"Attempt {i}: {delay:.2f}s")
    """
    # Exponential backoff: delay = base * 2^attempt
    delay = min(base_delay * (2**attempt), max_delay)

    # Add jitter: ±jitter_factor of the delay
    if jitter_factor > 0:
        jitter = delay * jitter_factor * (2 * random.random() - 1)
        delay = max(0.1, delay + jitter)  # Never less than 0.1s

    return delay


def retry_with_backoff(
    func: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.3,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Retry a function with exponential backoff.

    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter_factor: Amount of randomness to add to delays (0.0-1.0)
        retryable_exceptions: Tuple of exception types to retry on

    Returns:
        Result of func()

    Raises:
        The last exception if all retries are exhausted
    """
    last_exception = None

    for attempt in range(max_attempts):
        try:
            return func()
        except retryable_exceptions as exc:
            last_exception = exc
            if attempt < max_attempts - 1:
                delay = exponential_backoff_with_jitter(attempt, base_delay, max_delay, jitter_factor)
                time.sleep(delay)

    # All retries exhausted
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic failed without exception")  # Should never happen
