import collections
import threading
import time


class LoopTimer:
    """Tracks per-iteration delta time and computes running statistics.

    Thread-safe: tick() may be called from a worker thread while
    dt/avg/p95/reset are called from the main thread.
    """

    def __init__(self, maxlen: int = 100000):
        self._lock = threading.Lock()
        self._last_time: float = time.monotonic()
        self._dt: float = 0.0
        self._samples: collections.deque[float] = collections.deque(maxlen=maxlen)

    def tick(self) -> None:
        """Record a new loop iteration. Call once at the top of each loop."""
        now = time.monotonic()
        self._dt = now - self._last_time
        self._last_time = now
        with self._lock:
            self._samples.append(self._dt)

    @property
    def dt(self) -> float:
        """Most recent delta time in seconds."""
        return self._dt

    @property
    def avg(self) -> float:
        """Average delta time since last reset (seconds)."""
        with self._lock:
            samples = list(self._samples)
        if not samples:
            return self._dt
        return sum(samples) / len(samples)

    @property
    def p95(self) -> float:
        """95th-percentile delta time since last reset (seconds)."""
        with self._lock:
            samples = list(self._samples)
        if not samples:
            return self._dt
        samples.sort()
        idx = min(int(len(samples) * 0.95), len(samples) - 1)
        return samples[idx]

    def reset(self) -> None:
        """Clear the sample buffer. Call after consuming stats."""
        with self._lock:
            self._samples.clear()
