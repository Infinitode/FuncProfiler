"""Aggregated profiling statistics for FuncProfiler.

Every profiled call can be accumulated in a small, process-wide registry so a
script can answer "which function is actually slow overall?" without parsing
exported reports. Collection is cheap (one dictionary update per call) and can
be disabled per decorator with ``capture_stats=False``.
"""

import threading
import time
from typing import Dict, Optional

from ._utils import format_duration, format_memory, validate_sort_by, validate_top_n
from .exporters import export_table

_STATS_LOCK = threading.Lock()
_STATS: Dict[str, "FunctionStats"] = {}

_SORT_KEYS = ("total_time", "mean_time", "max_time", "calls", "peak_memory")

_SUMMARY_KEYS = (
    "Function",
    "Calls",
    "Errors",
    "Total (s)",
    "Mean (s)",
    "Min (s)",
    "Max (s)",
    "Peak Mem (MB)",
)

_SUMMARY_COLUMNS = (
    "Function",
    "Calls",
    "Errors",
    "Total",
    "Mean",
    "Min",
    "Max",
    "Peak Mem",
)


class FunctionStats:
    """Accumulated statistics for a single profiled function or block."""

    __slots__ = (
        "calls",
        "errors",
        "first_call",
        "last_call",
        "last_memory",
        "last_time",
        "max_time",
        "min_time",
        "name",
        "peak_memory",
        "total_memory",
        "total_time",
    )

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0
        self.errors = 0
        self.total_time = 0.0
        self.min_time: Optional[float] = None
        self.max_time: Optional[float] = None
        self.last_time: Optional[float] = None
        self.total_memory = 0.0
        self.peak_memory: Optional[float] = None
        self.last_memory: Optional[float] = None
        self.first_call = time.time()
        self.last_call = self.first_call

    # -- mutation ---------------------------------------------------------
    def record(self, duration, peak_memory=None, memory=None, error=False):
        """Record one profiled call."""
        self.calls += 1
        if error:
            self.errors += 1
        self.total_time += duration
        self.last_time = duration
        if self.min_time is None or duration < self.min_time:
            self.min_time = duration
        if self.max_time is None or duration > self.max_time:
            self.max_time = duration
        if peak_memory is not None:
            if self.peak_memory is None or peak_memory > self.peak_memory:
                self.peak_memory = peak_memory
            self.total_memory += peak_memory
        if memory is not None:
            self.last_memory = memory
        self.last_call = time.time()

    # -- derived values ---------------------------------------------------
    @property
    def mean_time(self):
        return self.total_time / self.calls if self.calls else 0.0

    @property
    def mean_memory(self):
        return self.total_memory / self.calls if self.calls else 0.0

    def as_dict(self):
        """Return a plain ``dict`` snapshot (safe to serialise or mutate)."""
        return {
            "name": self.name,
            "calls": self.calls,
            "errors": self.errors,
            "total_time": self.total_time,
            "mean_time": self.mean_time,
            "min_time": self.min_time,
            "max_time": self.max_time,
            "last_time": self.last_time,
            "mean_memory": self.mean_memory,
            "peak_memory": self.peak_memory,
            "last_memory": self.last_memory,
            "first_call": self.first_call,
            "last_call": self.last_call,
        }

    def __repr__(self):  # pragma: no cover - debugging aid
        return (
            f"<FunctionStats {self.name!r} calls={self.calls} "
            f"total={self.total_time:.9f}s>"
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def record_call(name, duration, peak_memory=None, memory=None, error=False):
    """Record a profiled call in the process-wide registry."""
    with _STATS_LOCK:
        stats = _STATS.get(name)
        if stats is None:
            stats = FunctionStats(name)
            _STATS[name] = stats
        stats.record(duration, peak_memory=peak_memory, memory=memory, error=error)


def get_stats():
    """Return a snapshot of all collected statistics keyed by function name.

    The returned dictionaries are copies, so callers can safely mutate them.
    """
    with _STATS_LOCK:
        return {name: stats.as_dict() for name, stats in _STATS.items()}


def reset_stats():
    """Forget all collected statistics."""
    with _STATS_LOCK:
        _STATS.clear()


def _sorted_stats(sort_by, top_n):
    sort_by = validate_sort_by(sort_by, _SORT_KEYS)
    top_n = validate_top_n(top_n)
    with _STATS_LOCK:
        items = [stats.as_dict() for stats in _STATS.values()]

    def sort_key(item):
        value = item.get(sort_by)
        return value if value is not None else float("-inf")

    # Sort by name first so equal values keep a deterministic order.
    items.sort(key=lambda item: item["name"])
    items.sort(key=sort_key, reverse=True)
    if top_n is not None:
        items = items[:top_n]
    return items


def summary_rows(sort_by="total_time", top_n=None):
    """Return machine-readable summary rows (seconds and megabytes)."""
    rows = []
    for item in _sorted_stats(sort_by, top_n):
        rows.append(
            {
                "Function": item["name"],
                "Calls": item["calls"],
                "Errors": item["errors"],
                "Total (s)": round(item["total_time"], 9),
                "Mean (s)": round(item["mean_time"], 9),
                "Min (s)": None if item["min_time"] is None else round(item["min_time"], 9),
                "Max (s)": None if item["max_time"] is None else round(item["max_time"], 9),
                "Peak Mem (MB)": (
                    None if item["peak_memory"] is None else round(item["peak_memory"], 6)
                ),
            }
        )
    return rows


def print_summary(sort_by="total_time", top_n=None, file=None):
    """Print a human-readable summary table of all collected statistics."""
    rows = _sorted_stats(sort_by, top_n)
    if not rows:
        print("[FUNCPROFILER] No profiling data has been collected yet.", file=file)
        return

    display = []
    for item in rows:
        display.append(
            {
                "Function": item["name"],
                "Calls": str(item["calls"]),
                "Errors": str(item["errors"]),
                "Total": format_duration(item["total_time"]),
                "Mean": format_duration(item["mean_time"]),
                "Min": format_duration(item["min_time"]),
                "Max": format_duration(item["max_time"]),
                "Peak Mem": format_memory(item["peak_memory"]),
            }
        )

    widths = [
        max([len(column)] + [len(row[column]) for row in display])
        for column in _SUMMARY_COLUMNS
    ]
    print("[FUNCPROFILER] Profile summary", file=file)
    print(
        "  ".join(column.ljust(widths[i]) for i, column in enumerate(_SUMMARY_COLUMNS)),
        file=file,
    )
    print("  ".join("-" * width for width in widths), file=file)
    for row in display:
        print(
            "  ".join(
                row[column].ljust(widths[i])
                for i, column in enumerate(_SUMMARY_COLUMNS)
            ),
            file=file,
        )
    total_calls = sum(item["calls"] for item in rows)
    total_time = sum(item["total_time"] for item in rows)
    print(
        f"{len(rows)} function(s), {total_calls} profiled call(s), "
        f"{format_duration(total_time)} of measured execution time.",
        file=file,
    )


def export_summary(
    export_format,
    filename,
    sort_by="total_time",
    top_n=None,
    append=False,
    export_dir=None,
):
    """Export the collected statistics and return the written path."""
    rows = summary_rows(sort_by=sort_by, top_n=top_n)
    return export_table(
        rows,
        export_format,
        filename,
        title="FuncProfiler Summary",
        append=append,
        export_dir=export_dir,
        headers=_SUMMARY_KEYS,
    )


#: Backwards/forwards friendly alias used in documentation snippets.
profile_summary = print_summary

__all__ = [
    "FunctionStats",
    "export_summary",
    "get_stats",
    "print_summary",
    "profile_summary",
    "record_call",
    "reset_stats",
    "summary_rows",
]
