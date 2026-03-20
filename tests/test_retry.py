"""Tests for retry utilities with exponential backoff."""

import importlib.util
import sys
import time
from pathlib import Path

import pytest

# Import retry module directly without triggering voice_agent.__init__
retry_path = Path(__file__).parent.parent / "voice_agent" / "retry.py"
spec = importlib.util.spec_from_file_location("retry", retry_path)
assert spec and spec.loader
retry = importlib.util.module_from_spec(spec)
sys.modules["retry"] = retry
spec.loader.exec_module(retry)

exponential_backoff_with_jitter = retry.exponential_backoff_with_jitter
retry_with_backoff = retry.retry_with_backoff


class TestExponentialBackoffWithJitter:
    """Test exponential backoff calculation."""

    def test_increases_exponentially(self):
        """Delay increases exponentially with attempt number."""
        delays = [exponential_backoff_with_jitter(i, base_delay=1.0, jitter_factor=0) for i in range(5)]
        # With no jitter: [1, 2, 4, 8, 16]
        assert delays[0] == pytest.approx(1.0)
        assert delays[1] == pytest.approx(2.0)
        assert delays[2] == pytest.approx(4.0)
        assert delays[3] == pytest.approx(8.0)
        assert delays[4] == pytest.approx(16.0)

    def test_respects_max_delay(self):
        """Delay is capped at max_delay."""
        delay = exponential_backoff_with_jitter(10, base_delay=1.0, max_delay=5.0, jitter_factor=0)
        assert delay == pytest.approx(5.0)

    def test_jitter_adds_randomness(self):
        """Jitter factor adds randomness to delay."""
        # With jitter, delays should vary
        delays = [exponential_backoff_with_jitter(3, base_delay=1.0, jitter_factor=0.3) for _ in range(10)]

        # All delays should be around 8.0 but with variation
        for delay in delays:
            # With 30% jitter: 8.0 ± 2.4 = [5.6, 10.4]
            assert 5.0 < delay < 11.0

        # Check that we got some variation (not all the same)
        assert len(set(delays)) > 1

    def test_never_less_than_minimum(self):
        """Delay is never less than 0.1s even with negative jitter."""
        # Extreme jitter shouldn't produce negative delays
        delay = exponential_backoff_with_jitter(0, base_delay=0.2, jitter_factor=1.0)
        assert delay >= 0.1


class TestRetryWithBackoff:
    """Test retry with backoff function."""

    def test_succeeds_on_first_attempt(self):
        """Function succeeds on first attempt without retries."""
        call_count = 0

        def succeeds():
            nonlocal call_count
            call_count += 1
            return "success"

        result = retry_with_backoff(succeeds, max_attempts=3)
        assert result == "success"
        assert call_count == 1

    def test_retries_on_exception(self):
        """Function is retried on exception."""
        call_count = 0

        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary failure")
            return "success"

        result = retry_with_backoff(
            fails_twice,
            max_attempts=5,
            base_delay=0.01,  # Fast for testing
            retryable_exceptions=(ValueError,),
        )
        assert result == "success"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        """Raises exception after max attempts exhausted."""
        call_count = 0

        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent failure")

        with pytest.raises(ValueError, match="permanent failure"):
            retry_with_backoff(
                always_fails,
                max_attempts=3,
                base_delay=0.01,
                retryable_exceptions=(ValueError,),
            )

        assert call_count == 3

    def test_does_not_retry_non_retryable_exceptions(self):
        """Does not retry on non-retryable exceptions."""
        call_count = 0

        def fails_with_runtime_error():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("non-retryable")

        with pytest.raises(RuntimeError, match="non-retryable"):
            retry_with_backoff(
                fails_with_runtime_error,
                max_attempts=3,
                retryable_exceptions=(ValueError,),  # Only retry ValueError
            )

        # Should fail immediately without retries
        assert call_count == 1

    def test_uses_exponential_backoff(self):
        """Delay between retries increases exponentially."""
        call_times = []

        def fails_twice():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise ValueError("temporary failure")
            return "success"

        retry_with_backoff(
            fails_twice,
            max_attempts=5,
            base_delay=0.1,
            max_delay=1.0,
            retryable_exceptions=(ValueError,),
        )

        # We should have 3 call times
        assert len(call_times) == 3

        # Check that delays increased (approximately, accounting for jitter)
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]

        # First delay ~0.1s, second delay ~0.2s (with jitter)
        assert 0.05 < delay1 < 0.2
        assert 0.1 < delay2 < 0.4
        # Second delay should be longer than first
        assert delay2 > delay1 * 0.8  # Allow some jitter variation
