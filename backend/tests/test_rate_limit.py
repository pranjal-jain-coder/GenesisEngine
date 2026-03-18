"""
Tests for the per-minute rate-limiting logic added to UsageTracker.

We use time.monotonic() patching so tests run instantly without real sleeps.
"""
import time
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch

from core.usage_tracker import UsageTracker, _MINUTE_WINDOW


class TestRateLimitDetection(unittest.TestCase):
    """is_rate_limited / seconds_until_slot / _prune_window"""

    def setUp(self):
        self.path = Path("/tmp/test_rl_usage.json")
        if self.path.exists():
            self.path.unlink()
        self.tracker = UsageTracker(self.path, daily_limit=20, rate_limit=5)

    def tearDown(self):
        if self.path.exists():
            self.path.unlink()

    def test_not_limited_when_empty(self):
        self.assertFalse(self.tracker.is_rate_limited("testkey1"))

    def test_not_limited_below_threshold(self):
        key = "testkey2"
        key_id = self.tracker._key_id(key)
        now = time.monotonic()
        # Put 4 timestamps in the window (rate_limit = 5)
        self.tracker._minute_log[key_id] = deque([now - 10, now - 8, now - 5, now - 2])
        self.assertFalse(self.tracker.is_rate_limited(key))

    def test_limited_at_threshold(self):
        key = "testkey3"
        key_id = self.tracker._key_id(key)
        now = time.monotonic()
        # Exactly 5 timestamps inside the 60-second window
        self.tracker._minute_log[key_id] = deque([now - 50, now - 40, now - 30, now - 20, now - 10])
        self.assertTrue(self.tracker.is_rate_limited(key))

    def test_stale_timestamps_pruned(self):
        key = "testkey4"
        key_id = self.tracker._key_id(key)
        now = time.monotonic()
        # 5 timestamps but all older than 60 s — should be pruned
        self.tracker._minute_log[key_id] = deque([now - 90, now - 80, now - 70, now - 65, now - 61])
        self.assertFalse(self.tracker.is_rate_limited(key))

    def test_seconds_until_slot_zero_when_free(self):
        key = "testkey5"
        self.assertEqual(self.tracker.seconds_until_slot(key), 0.0)

    def test_seconds_until_slot_positive_when_limited(self):
        key = "testkey6"
        key_id = self.tracker._key_id(key)
        now = time.monotonic()
        # Oldest call was 10 s ago, 5 calls in window → need to wait ~50 s
        self.tracker._minute_log[key_id] = deque([now - 10, now - 8, now - 5, now - 3, now - 1])
        wait = self.tracker.seconds_until_slot(key)
        self.assertGreater(wait, 40.0)  # roughly 60 - 10 = 50 s remaining
        self.assertLessEqual(wait, 55.0)

    def test_increment_usage_records_timestamp(self):
        key = "testkey7"
        key_id = self.tracker._key_id(key)
        before = time.monotonic()
        self.tracker.increment_usage(key)
        after = time.monotonic()
        log = self.tracker._minute_log.get(key_id)
        self.assertIsNotNone(log)
        self.assertEqual(len(log), 1)
        self.assertGreaterEqual(log[0], before)
        self.assertLessEqual(log[0], after)


class TestWaitForSlot(unittest.TestCase):
    """wait_for_slot: key rotation and sleep behaviour"""

    def setUp(self):
        self.path = Path("/tmp/test_wfs_usage.json")
        if self.path.exists():
            self.path.unlink()
        self.tracker = UsageTracker(self.path, daily_limit=20, rate_limit=5)

    def tearDown(self):
        if self.path.exists():
            self.path.unlink()

    def test_returns_first_free_key(self):
        """When all keys have free minute slots, return the first one."""
        result = self.tracker.wait_for_slot(["alpha_key_111", "beta_key_222"])
        self.assertEqual(result, "alpha_key_111")

    def test_rotates_to_second_key_when_first_is_minute_limited(self):
        """Should skip minute-limited key and return next available key."""
        key1 = "alpha_key_111"
        key1_id = self.tracker._key_id(key1)
        now = time.monotonic()
        # Saturate key1's minute window
        self.tracker._minute_log[key1_id] = deque([now - 50, now - 40, now - 30, now - 20, now - 10])
        result = self.tracker.wait_for_slot([key1, "beta_key_222"])
        self.assertEqual(result, "beta_key_222")

    def test_raises_when_all_keys_daily_exhausted(self):
        """All keys at daily limit → ValueError (no sleeping)."""
        keys = ["key_aaa_111", "key_bbb_222"]
        for k in keys:
            self.tracker.mark_exhausted(k)
        with self.assertRaises(ValueError):
            self.tracker.wait_for_slot(keys)

    def test_sleeps_when_all_keys_minute_limited(self):
        """
        When all daily-OK keys are minute-limited, wait_for_slot should sleep
        then return a key once the window clears.

        We mock time.sleep so this runs instantly.  After the 'sleep', we also
        advance the in-memory timestamps so _prune_window sees them as expired.
        """
        keys = ["key_ccc_111", "key_ddd_222"]
        now_base = time.monotonic()

        # Fill both keys' minute logs so they are rate-limited
        for k in keys:
            kid = self.tracker._key_id(k)
            self.tracker._minute_log[kid] = deque(
                [now_base - 50, now_base - 40, now_base - 30, now_base - 20, now_base - 10]
            )

        sleep_calls = []

        def fake_sleep(seconds):
            sleep_calls.append(seconds)
            # Simulate time passing: shift all log entries back by 60 s so the
            # next _prune_window call will drop them.
            for k in keys:
                kid = self.tracker._key_id(k)
                log = self.tracker._minute_log[kid]
                shifted = deque(ts - 60 for ts in log)
                self.tracker._minute_log[kid] = shifted

        with patch("core.usage_tracker.time.sleep", side_effect=fake_sleep):
            result = self.tracker.wait_for_slot(keys)

        # Should have slept exactly once, then returned key1
        self.assertEqual(len(sleep_calls), 1)
        self.assertIn(result, keys)


if __name__ == "__main__":
    unittest.main()
