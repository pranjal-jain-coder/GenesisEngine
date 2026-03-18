import json
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

_MINUTE_WINDOW = 60.0  # seconds


class UsageTracker:
    def __init__(self, usage_path: Path, daily_limit: int, rate_limit: int = 5):
        """
        Args:
            usage_path:   Path to the persistent JSON usage file.
            daily_limit:  Maximum requests per key per day.
            rate_limit:   Maximum requests per key per minute (sliding window).
        """
        self.usage_path = usage_path
        self.daily_limit = daily_limit
        self.rate_limit = rate_limit
        self._cache: Dict[str, Any] = {}
        # In-memory sliding window: key_id -> deque of call timestamps (float)
        self._minute_log: Dict[str, deque] = {}
        self._ensure_path()
        self._cache = self._load_usage()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _ensure_path(self):
        """Ensures the data directory and usage file exist."""
        self.usage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.usage_path.exists():
            self._save_usage({})

    def _load_usage(self) -> Dict[str, Any]:
        """Loads usage data from JSON."""
        try:
            if not self.usage_path.exists():
                return {}
            with open(self.usage_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading usage data: {e}")
            return {}

    def _save_usage(self, data: Dict[str, Any]):
        """Saves usage data to JSON and updates cache."""
        self._cache = data
        try:
            with open(self.usage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            logger.error(f"Error saving usage data: {e}")

    # ------------------------------------------------------------------
    # Key-ID helper
    # ------------------------------------------------------------------

    @staticmethod
    def _key_id(api_key: str) -> str:
        return f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else api_key

    # ------------------------------------------------------------------
    # Daily-limit helpers (unchanged behaviour)
    # ------------------------------------------------------------------

    def get_todays_usage(self) -> Dict[str, int]:
        """Gets request counts for each key for the current day from cache."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self._cache:
            self._cache[today] = {}
            self._save_usage(self._cache)
        return self._cache[today]

    def increment_usage(self, api_key: str):
        """Increments the daily usage count and records a per-minute timestamp."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self._cache:
            self._cache[today] = {}

        key_id = self._key_id(api_key)
        current_count = self._cache[today].get(key_id, 0)
        self._cache[today][key_id] = current_count + 1
        self._save_usage(self._cache)

        # Record timestamp for the per-minute window
        log = self._minute_log.setdefault(key_id, deque())
        log.append(time.monotonic())
        logger.info(f"Incremented usage for key {key_id}: {current_count + 1}")

    def get_available_key(self, api_keys: List[str]) -> Optional[str]:
        """Returns the first key below the *daily* limit (ignores per-minute)."""
        usage = self.get_todays_usage()
        for key in api_keys:
            key_id = self._key_id(key)
            if usage.get(key_id, 0) < self.daily_limit:
                return key
        return None

    def mark_exhausted(self, api_key: str):
        """Forcefully sets a key to the daily limit and persists."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self._cache:
            self._cache[today] = {}
        key_id = self._key_id(api_key)
        self._cache[today][key_id] = self.daily_limit
        self._save_usage(self._cache)
        logger.warning(f"Marked key {key_id} as exhausted.")

    def mark_rate_limited(self, api_key: str):
        """
        Manually marks a key as hitting the rate limit by filling its minute log.
        This forces wait_for_slot() to skip it or wait.
        """
        key_id = self._key_id(api_key)
        log = self._minute_log.setdefault(key_id, deque())
        now = time.monotonic()
        # Fill the log with current timestamps up to the limit so is_rate_limited() becomes True
        # We add enough entries to ensure len(log) >= rate_limit
        needed = max(0, self.rate_limit - len(log))
        for _ in range(needed):
            log.append(now)
        # Verify it's effectively rate-limited now
        if len(log) < self.rate_limit:
            log.append(now)
            
        logger.warning(f"Marked key {key_id} as rate-limited (filled minute log).")

    # ------------------------------------------------------------------
    # Per-minute rate-limit helpers
    # ------------------------------------------------------------------

    def _prune_window(self, key_id: str) -> deque:
        """Drop timestamps older than 60 s and return the pruned deque."""
        log = self._minute_log.setdefault(key_id, deque())
        cutoff = time.monotonic() - _MINUTE_WINDOW
        while log and log[0] <= cutoff:
            log.popleft()
        return log

    def is_rate_limited(self, api_key: str) -> bool:
        """Return True if the key has already hit the per-minute limit."""
        key_id = self._key_id(api_key)
        log = self._prune_window(key_id)
        return len(log) >= self.rate_limit

    def seconds_until_slot(self, api_key: str) -> float:
        """
        How many seconds until the oldest call in the window expires,
        freeing a slot.  Returns 0 if there is already a free slot.
        """
        key_id = self._key_id(api_key)
        log = self._prune_window(key_id)
        if len(log) < self.rate_limit:
            return 0.0
        oldest = log[0]
        wait = (_MINUTE_WINDOW - (time.monotonic() - oldest)) + 0.05  # tiny buffer
        return max(wait, 0.0)

    def wait_for_slot(self, api_keys: List[str]) -> str:
        """
        Return the best key to use next, respecting BOTH daily and per-minute limits.

        Strategy:
        1. Prefer a key that is below both limits right now → return immediately.
        2. If every daily-available key is currently minute-rate-limited, sleep
           until the shortest wait expires, then retry.
        3. If all keys are daily-exhausted, raise ValueError.

        Args:
            api_keys: Ordered list of API keys to consider.

        Returns:
            An API key string that is safe to call right now.

        Raises:
            ValueError: All keys have reached their daily limit.
        """
        while True:
            usage = self.get_todays_usage()
            day_ok_keys = [
                k for k in api_keys
                if usage.get(self._key_id(k), 0) < self.daily_limit
            ]

            if not day_ok_keys:
                raise ValueError(
                    "All Gemini API keys have reached their daily limit (RPD). "
                    "Please wait for reset or add more keys."
                )

            # Try to find a key that is also below the per-minute limit
            for key in day_ok_keys:
                if not self.is_rate_limited(key):
                    return key

            # All daily-available keys are minute-rate-limited; find shortest wait
            min_wait = min(self.seconds_until_slot(k) for k in day_ok_keys)
            logger.warning(
                f"All {len(day_ok_keys)} available key(s) are at the "
                f"{self.rate_limit} RPM limit. Waiting {min_wait:.1f}s for a slot to open..."
            )
            time.sleep(min_wait)
            # Loop back and re-check

