# FuncProfiler
![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)
[![Code Size](https://img.shields.io/github/languages/code-size/infinitode/funcprofiler)](https://github.com/infinitode/funcprofiler)
![Downloads](https://pepy.tech/badge/funcprofiler)
![License Compliance](https://img.shields.io/badge/license-compliance-brightgreen.svg)
![PyPI Version](https://img.shields.io/pypi/v/funcprofiler)

An open-source Python library for identifying bottlenecks in code. It includes function profiling, line-by-line profiling, aggregated statistics, logging and report exports — with no third-party dependencies.

## Changelog (v1.3.0)

### Fixed

- **`@function_profile` without parentheses** no longer raises `TypeError`; both `@function_profile` and `@function_profile(...)` work.
- **Exceptions no longer leak profiling state.** Previously a raised exception skipped `tracemalloc.stop()` and `sys.settrace(None)`, so tracing stayed enabled for the rest of the process and every later measurement was wrong. Cleanup now always happens.
- **Nested and recursive profiled calls no longer corrupt measurements.** A nested call used to stop the outer call's `tracemalloc` session (reporting `0.0 MB`), and a caller-owned `tracemalloc` session was silently stopped. Nested calls now join the existing session and report "not attributable" (`n/a`) instead of a fake zero.
- **Line-by-line tracing only instruments the profiled function.** Unrelated frames (libraries, comprehensions, helpers, the standard library) are no longer traced. Tracing overhead drops to roughly 1.2× when memory tracking is disabled, against roughly 5× before.
- **Recursion is aggregated into one line-by-line report** instead of re-instrumenting and printing a separate report for each recursive call.
- **Existing trace hooks are preserved.** Coverage tools and debuggers that set a trace function no longer have it destroyed; the previous tracer is restored.
- **Export filenames no longer double their extension** (`report.json` used to create `report.json.json`), and missing target directories are created automatically.
- **HTML reports escape profiled values**, so return values, arguments, source code and docstrings can no longer break or inject into the report. Markdown exports escape `|`.
- **YAML/TOML/XML exports are valid documents.** Keys containing spaces are quoted, multi-line values use proper block scalars, XML uses legal element names and a declaration.
- **Functions without retrievable source** (`exec`, frozen apps, some REPL sessions) no longer crash line-by-line exports; their source is shown as `???`.
- **CSV output uses the `csv` module** instead of hand-wrapped quotes, and repeated exports no longer silently mix runs without a header or run marker.
- **`export_format` and `log_level` are validated when the decorator is created**, so a typo fails immediately instead of after the profiled function has already run.
- **Shared logs are actually shared**: one file per process rather than one per function (the filename used to be derived from the clock at decoration time).
- **Per-line memory is no longer the cumulative `tracemalloc` peak** (which could only ever increase); it now samples the heap while the line executes.
- Empty line-by-line reports no longer raise `IndexError` when exporting.

### Added

- **`profile_block`** context manager for profiling arbitrary code blocks.
- **Aggregated statistics**: `get_stats`, `reset_stats`, `summary_rows`, `print_summary` and `export_summary` answer "which function is slow overall?" without parsing reports.
- **New decorator options**: `track_memory`, `sample_every`, `include_args`, `include_return_value`, `max_value_length`, `append`, `export_dir`, `logger`, `sort_by` and `top_n`.
- **`log_level="silent"`** and the ability to send console output to a `logging.Logger` with `logger=`.
- **Async and generator support.** Coroutines are timed across their whole awaited lifetime and generators from first `next()` to exhaustion. Async generators emit a `RuntimeWarning` instead of silently reporting ~0 s.
- **Hotspot columns**: line reports now include a `Percent` column and use human-readable units (`µs`, `ms`, `s`) in the console.
- **Helpers and metadata**: `format_duration`, `format_memory`, `EXPORT_FORMATS`, `__version__` and a `py.typed` marker.

### Changed

- Exports overwrite the target file by default; pass `append=True` to accumulate runs (`txt`, `json`, `csv`, `md`, `html`).
- Line-by-line exports include `Percent` and `Timestamp` columns so appended rows stay distinguishable.
- Exporters no longer print; the decorators report `Report exported to: …` instead.
- The console line-by-line report is aligned and unit-aware (see examples below).
- Minimum supported Python is now 3.8; CI tests every supported version.

### Migrating from 1.2.0

- Nothing has to change for typical usage. Line-by-line `csv`/`html` exports now overwrite instead of appending; add `append=True` to restore accumulation.
- If you parsed the old console output, note that line reports are now a table with `Time`, `%` and `Memory` columns.
- `export_profiling_data` and `export_function_profile_data` keep their signatures and now return the written path.

## Changelog (v.1.2.0):
- Significant performance improvements for both function and line-by-line profiling.
- Cached function metadata at decoration time to reduce overhead during execution.
- Optimized line-by-line tracing using code object identity comparison.
- Implemented buffered logging for shared logs to minimize frequent file I/O.
- Improved trace accuracy by properly capturing the final line's execution time.
- Refactored export logic for more efficient report generation.

## Changelog (v.1.1.0):
- Added support for 2 new export formats: `yaml` and `toml`.
- Exports now include more information: peak memory usage, timestamp, arguments, return value, filepath, line number, and docstring.
- Added `enabled` and `log_level` options to the decorators.
- Improved export formats for better readability.

## Installation

You can install FuncProfiler using pip:

```bash
pip install funcprofiler
```

## Supported Python Versions

FuncProfiler supports Python 3.8 and later (tested on 3.8 – 3.13).

## Features

- **Function Profiling**: monitor a function's execution time and memory usage.
- **Line-by-Line Profiling**: execution time, percentage of total, and memory for every line.
- **Block Profiling**: profile any `with` block, not just functions.
- **Aggregated Statistics**: totals, means, min/max and peak memory per function.
- **Shared Logging**: log profiler output to a single `.txt` file.
- **File Exports**: eight report formats.
- **Async & Generators**: coroutine and generator functions are measured correctly.
- **Low-overhead options**: `sample_every`, `track_memory=False`, `enabled=False`.

## Export Formats

| Format | `function_profile` | `line_by_line_profile` | `append=True` |
|--------|--------------------|------------------------|---------------|
| `txt`  |         ✅         |           ✅           |      ✅       |
| `json` |         ✅         |           ✅           |      ✅       |
| `csv`  |         ✅         |           ✅           |      ✅       |
| `html` |         ✅         |           ✅           |      ✅       |
| `xml`  |         ✅         |           ✅           |      ❌       |
| `md`   |         ✅         |           ✅           |      ✅       |
| `yaml` |         ✅         |           ✅           |      ✅       |
| `toml` |         ✅         |           ✅           |      ✅       |

## Usage

### Function Profiling

```python
from funcprofiler import function_profile

@function_profile(export_format="html", shared_log=True, log_level="debug")
def some_function():
    return "Hello World."

message = some_function()
```

A bare `@function_profile` (without parentheses) also works.

### Line-by-Line Profiling

```python
from funcprofiler import line_by_line_profile

@line_by_line_profile(shared_log=True, enabled=True)
def some_complicated_function(n):
    total = 0
    for i in range(n):
        for j in range(i):
            total += (i * j) ** 0.5
    return total

total = some_complicated_function(1000)
```

Console output is a compact table of hotspots:

```
[FUNCPROFILER] Line-by-line profile for 'some_complicated_function' (6 line(s), total 82.13 ms, peak 0.0060 MB)
  Line  Source                                 Time        %       Memory
  4     total = 0                              1.20 µs     0.00%   0.0021 MB
  5     for i in range(n):                     21.44 ms    26.10%  0.0024 MB
  7     total += (i * j) ** 0.5                60.02 ms    73.07%  0.0024 MB
  8     return total                           3.37 µs     0.00%   0.0024 MB
```

Use `sort_by="time"` to order by cost and `top_n=10` to keep the output short.

### Block Profiling

```python
from funcprofiler import profile_block

with profile_block("load-data", export_format="json", filename="load") as block:
    rows = expensive_io()

print(block.execution_time, block.peak_memory_usage)
```

### Aggregated Statistics

Every profiled call is accumulated in a process-wide registry (disable with
`capture_stats=False`):

```python
from funcprofiler import function_profile, get_stats, print_summary, export_summary

@function_profile(log_level="silent")
def parse_row(row):
    ...

for row in rows:
    parse_row(row)

print_summary(sort_by="total_time", top_n=10)
export_summary("csv", "profile_summary")

stats = get_stats()          # {"myapp.parse_row": {"calls": 10_000, ...}}
```

```
[FUNCPROFILER] Profile summary
Function            Calls  Errors  Total     Mean      Min       Max       Peak Mem
------------------  -----  ------  --------  --------  --------  --------  ---------
myapp.parse_row     10000  0       1.204 s   120.40 µs 96.10 µs  1.201 ms  0.0210 MB
```

### Options

| Option | Applies to | Description |
|--------|-----------|-------------|
| `export_format` | both | `txt`, `json`, `csv`, `html`, `xml`, `md`, `yaml`, `toml` (case-insensitive). |
| `filename` | both | Output filename, with or without extension. |
| `shared_log` | both | Append to one process-wide `.txt` log. |
| `enabled` | both | `False` disables profiling entirely. |
| `log_level` | both | `"info"`, `"debug"` or `"silent"`. |
| `logger` | both | Send console output to a `logging.Logger`. |
| `capture_stats` | both | Accumulate results in `get_stats()` (default `True`). |
| `track_memory` | both | Measure memory with `tracemalloc` (default `True`). |
| `sample_every` | both | Profile only every Nth call. |
| `include_args` | both | Include call arguments in logs/exports. |
| `include_return_value` | both | Include the return value in logs/exports. |
| `max_value_length` | both | Truncate recorded reprs (default 500 chars). |
| `append` | both | Append a run to an existing export. |
| `export_dir` | both | Directory for relative export filenames. |
| `sort_by` | line-by-line | `"line"` (default) or `"time"` for the console table. |
| `top_n` | line-by-line | Show only the N slowest lines in the console. |

### Notes and limitations

- `line_by_line_profile` uses `sys.settrace`, so it slows the profiled function
  down considerably. Use it on suspicious functions, not production hot paths.
- Memory tracking is the most expensive part of profiling. Pass
  `track_memory=False` for timing-only measurements.
- Line timings are wall-clock samples: time spent inside calls is attributed to
  the calling line, and time spent suspended inside an `await` is not attributed
  to any line.
- Recursive calls are aggregated into the outermost profile; the time spent in
  recursion is attributed to the recursive line.
- `line_by_line_profile` traces only the calling thread. Work performed on other
  threads is not attributed to lines.
- Async generators are not profiled (a `RuntimeWarning` is emitted); wrap the
  body in a regular coroutine instead.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request on [GitHub](https://github.com/infinitode/funcprofiler). Run the test suite with:

```bash
python -m unittest test -v
```

## License

FuncProfiler is released under the **MIT License (Modified)**. See the [LICENSE](https://github.com/infinitode/funcprofiler/blob/main/LICENSE) file for details.
