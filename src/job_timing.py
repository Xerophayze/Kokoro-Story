"""Cumulative active-time metrics without replaying pre-resume completions."""
import time
from datetime import datetime


class JobTiming:
    def __init__(self, previous=None, completed=0, *, clock=time.monotonic):
        previous = (previous or {}) if completed else {}
        self.clock = clock
        self.start = self.last = clock()
        self.started_at = previous.get("started_at") or datetime.now().isoformat()
        self.prior_elapsed = float(previous.get("total_seconds") or 0)
        self.prior = [float(t) for t in (previous.get("chunk_times") or []) if t is not None and float(t) >= 0][:completed]
        self.current = []
        self.completed_before = completed

    def complete(self):
        now = self.clock()
        self.current.append(max(0, now - self.last))
        self.last = now

    def eta(self, remaining):
        samples = self.current or self.prior
        return int(sum(samples) / len(samples) * remaining) if samples else None

    def snapshot(self, *, finished=False):
        samples = self.prior + self.current
        return {
            "started_at": self.started_at,
            "completed_at": datetime.now().isoformat() if finished else None,
            "total_seconds": round(self.prior_elapsed + max(0, self.clock() - self.start), 2),
            "chunk_count": self.completed_before + len(self.current),
            "session_chunk_count": len(self.current),
            "avg_chunk_seconds": round(sum(samples) / len(samples), 2) if samples else None,
            "min_chunk_seconds": round(min(samples), 2) if samples else None,
            "max_chunk_seconds": round(max(samples), 2) if samples else None,
            "chunk_times": [round(t, 2) for t in samples],
        }
