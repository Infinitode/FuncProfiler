"""FuncProfiler - find the bottlenecks in your Python code.

The package exposes two decorators, one context manager and a handful of
helpers:

* :func:`function_profile` - measure a function's execution time and memory.
* :func:`line_by_line_profile` - attribute time and memory to individual lines.
* :func:`profile_block` - profile an arbitrary ``with`` block.
* :func:`get_stats`, :func:`print_summary`, :func:`export_summary` - aggregate
  statistics across every profiled call.
* :func:`export_function_profile_data`, :func:`export_profiling_data`,
  :func:`export_table` - write reports by hand.

Quick start::

    from funcprofiler import function_profile, print_summary

    @function_profile(export_format="html", log_level="info")
    def expensive(n):
        return sum(i * i for i in range(n))

    expensive(100_000)
    print_summary()
"""

from ._utils import VALID_FORMATS, format_duration, format_memory, normalise_format
from .core import ProfileBlock, function_profile, line_by_line_profile, profile_block
from .exporters import (
    export_function_profile_data,
    export_profiling_data,
    export_table,
)
from .stats import (
    FunctionStats,
    export_summary,
    get_stats,
    print_summary,
    profile_summary,
    reset_stats,
    summary_rows,
)

#: Version of the package. Kept in sync with the published distribution.
__version__ = "1.3.0"

#: Convenience alias so users can validate a format without importing internals.
EXPORT_FORMATS = VALID_FORMATS

__all__ = [
    "EXPORT_FORMATS",
    "FunctionStats",
    "ProfileBlock",
    "__version__",
    "export_function_profile_data",
    "export_profiling_data",
    "export_summary",
    "export_table",
    "format_duration",
    "format_memory",
    "function_profile",
    "get_stats",
    "line_by_line_profile",
    "normalise_format",
    "print_summary",
    "profile_block",
    "profile_summary",
    "reset_stats",
    "summary_rows",
]
