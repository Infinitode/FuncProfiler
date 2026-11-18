"""Test suite for FuncProfiler.

Run with either of::

    python -m unittest test -v
    python test.py
"""

import asyncio
import contextlib
import glob
import inspect
import io
import json
import logging
import os
import sys
import tempfile
import threading
import time
import tracemalloc
import unittest
import xml.etree.ElementTree as ET

from funcprofiler import (
    EXPORT_FORMATS,
    export_function_profile_data,
    export_profiling_data,
    export_summary,
    format_duration,
    format_memory,
    function_profile,
    get_stats,
    line_by_line_profile,
    normalise_format,
    print_summary,
    profile_block,
    reset_stats,
    summary_rows,
)
from funcprofiler._utils import reset_shared_log_path

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - older interpreters
    tomllib = None


def stats_key(func):
    """The registry key used for a profiled callable."""
    return f"{func.__module__}.{func.__qualname__}"


def parse_toml(path):
    if tomllib is None:
        return None
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def parse_yaml(path):
    """Parse YAML when PyYAML happens to be installed (it is not a dependency)."""
    try:
        import yaml
    except ImportError:  # pragma: no cover - optional dependency
        return None
    with open(path) as handle:
        return yaml.safe_load(handle)


# ---------------------------------------------------------------------------
# Module level functions so the profilers can read their source code.
# ---------------------------------------------------------------------------
def _sum_squares(n):
    total = 0
    for i in range(n):
        total += i * i
    return total


def _nested_helper_user(n):
    def helper(x):
        return x * x

    total = 0
    for i in range(n):
        total += helper(i)
    return total


def _raising():
    raise ValueError("expected failure")


def _fib(n):
    if n < 2:
        return n
    return _fib(n - 1) + _fib(n - 2)


class TempDirTestCase(unittest.TestCase):
    """Base class giving each test an isolated working directory and stdout."""

    def setUp(self):
        self._old_cwd = os.getcwd()
        self._tmpdir = tempfile.TemporaryDirectory()
        os.chdir(self._tmpdir.name)
        reset_stats()
        reset_shared_log_path()
        self._stdout = io.StringIO()
        self._redirect = contextlib.redirect_stdout(self._stdout)
        self._redirect.__enter__()

    def tearDown(self):
        self._redirect.__exit__(None, None, None)
        os.chdir(self._old_cwd)
        self._tmpdir.cleanup()
        reset_stats()
        reset_shared_log_path()

    def output(self):
        return self._stdout.getvalue()

    def assert_file(self, name):
        self.assertTrue(os.path.exists(name), f"{name} was not created")
        return name


class TestFunctionProfile(TempDirTestCase):
    def test_returns_original_result(self):
        @function_profile(log_level="silent")
        def add(a, b):
            return a + b

        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add.__name__, "add")

    def test_bare_decorator(self):
        @function_profile
        def add(a, b):
            return a + b

        self.assertEqual(add(1, 2), 3)

    def test_info_output(self):
        @function_profile()
        def run():
            return 1

        run()
        output = self.output()
        self.assertIn("[FUNCPROFILER] Function 'run' executed in", output)
        self.assertIn("Current memory usage:", output)
        self.assertIn("Peak:", output)

    def test_silent_output(self):
        @function_profile(log_level="silent", export_format="json", filename="silent")
        def run():
            return 1

        run()
        self.assertEqual(self.output(), "")
        self.assert_file("silent.json")

    def test_debug_output_includes_return_value(self):
        @function_profile(log_level="debug")
        def run(value):
            return value * 2

        run(21)
        output = self.output()
        self.assertIn("[FUNCPROFILER-DEBUG] Return Value: 42", output)
        self.assertIn("called with args:", output)
        self.assertNotIn("[FUNCPROFILER] Function 'run'", output)

    def test_logger_sink(self):
        stream = io.StringIO()
        logger = logging.getLogger("funcprofiler-test")
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)
        try:
            @function_profile(log_level="info", logger=logger)
            def run():
                return 1

            run()
        finally:
            logger.removeHandler(handler)
        self.assertIn("executed in", stream.getvalue())
        self.assertEqual(self.output(), "")

    def test_enabled_false_is_a_no_op(self):
        @function_profile(enabled=False, export_format="json", filename="never")
        def run():
            return 7

        self.assertEqual(run(), 7)
        self.assertFalse(os.path.exists("never.json"))
        self.assertEqual(get_stats(), {})

    def test_exception_propagates_and_cleans_up(self):
        @function_profile(log_level="silent")
        def boom():
            _raising()

        self.assertFalse(tracemalloc.is_tracing())
        with self.assertRaises(ValueError):
            boom()
        self.assertFalse(
            tracemalloc.is_tracing(), "tracemalloc was left running after an exception"
        )
        stats = get_stats()
        self.assertEqual(len(stats), 1)
        self.assertEqual(next(iter(stats.values()))["errors"], 1)

    def test_caller_tracemalloc_session_is_preserved(self):
        tracemalloc.start()
        try:
            @function_profile(log_level="silent")
            def allocate():
                return [0] * 1000

            allocate()
            self.assertTrue(tracemalloc.is_tracing())
        finally:
            tracemalloc.stop()

    def test_nested_profiled_calls_keep_outer_measurement(self):
        @function_profile(log_level="silent")
        def inner():
            return [0] * 100_000

        @function_profile(log_level="silent")
        def outer():
            inner()
            return [0] * 100_000

        outer()
        stats = get_stats()
        outer_stats = stats[stats_key(outer)]
        inner_stats = stats[stats_key(inner)]
        self.assertIsNotNone(outer_stats["peak_memory"], "outer peak memory was lost")
        self.assertGreater(outer_stats["peak_memory"], 0.0)
        # Nested peaks are not attributable, so they are reported as unknown
        # rather than as a misleading zero.
        self.assertIsNone(inner_stats["peak_memory"])

    def test_track_memory_false(self):
        @function_profile(log_level="silent", track_memory=False)
        def run():
            return 1

        run()
        stats = next(iter(get_stats().values()))
        self.assertIsNone(stats["peak_memory"])
        self.assertIsNone(stats["last_memory"])

    def test_sample_every(self):
        @function_profile(log_level="silent", sample_every=3)
        def run():
            return 1

        for _ in range(10):
            run()
        self.assertEqual(next(iter(get_stats().values()))["calls"], 4)

    def test_arguments_and_return_value_can_be_omitted(self):
        @function_profile(
            log_level="silent",
            include_args=False,
            include_return_value=False,
            export_format="json",
            filename="quiet",
        )
        def run(secret):
            return secret

        run("hunter2")
        with open("quiet.json") as handle:
            profile = json.load(handle)["profile"]
        self.assertIsNone(profile["arguments"])
        self.assertIsNone(profile["return_value"])

    def test_value_truncation(self):
        @function_profile(
            log_level="silent", max_value_length=20, export_format="json", filename="t"
        )
        def run():
            return "x" * 500

        run()
        with open("t.json") as handle:
            value = json.load(handle)["profile"]["return_value"]
        self.assertLessEqual(len(value), 20)
        self.assertTrue(value.endswith("'"), value)

    def test_exports_all_formats(self):
        for fmt in EXPORT_FORMATS:
            with self.subTest(fmt=fmt):
                @function_profile(
                    export_format=fmt, filename=f"profile_{fmt}", log_level="silent"
                )
                def run():
                    return 1

                run()
                path = self.assert_file(f"profile_{fmt}.{fmt}")
                if fmt == "json":
                    with open(path) as handle:
                        data = json.load(handle)
                    self.assertIn("metadata", data)
                    self.assertIn("peak_memory_usage", data["profile"])
                elif fmt == "xml":
                    ET.parse(path)
                elif fmt == "toml":
                    data = parse_toml(path)
                    if data is not None:
                        self.assertEqual(data["function_name"], "run")
                elif fmt == "csv":
                    with open(path) as handle:
                        self.assertIn("function_name", handle.readline())
                elif fmt == "html":
                    with open(path) as handle:
                        content = handle.read()
                    self.assertIn("<!DOCTYPE html>", content)
                elif fmt == "yaml":
                    with open(path) as handle:
                        self.assertIn('function_name: "run"', handle.read())
                    parsed = parse_yaml(path)
                    if parsed is not None:
                        self.assertEqual(parsed["function_name"], "run")
                elif fmt == "md":
                    with open(path) as handle:
                        self.assertIn("# Function Profiling Report: run", handle.read())

    def test_export_progress_message(self):
        @function_profile(export_format="json", filename="visible")
        def run():
            return 1

        run()
        self.assertIn("Report exported to:", self.output())

    def test_filename_extension_is_not_doubled(self):
        @function_profile(
            export_format="json", filename="report.json", log_level="silent"
        )
        def run():
            return 1

        run()
        self.assert_file("report.json")
        self.assertFalse(os.path.exists("report.json.json"))

    def test_export_dir_is_created(self):
        @function_profile(
            export_format="md", filename="nested/report", log_level="silent"
        )
        def run():
            return 1

        run()
        self.assert_file(os.path.join("nested", "report.md"))

    def test_append_json_creates_runs(self):
        @function_profile(
            export_format="json", filename="runs", append=True, log_level="silent"
        )
        def run():
            return 1

        run()
        run()
        with open("runs.json") as handle:
            data = json.load(handle)
        self.assertEqual(len(data["runs"]), 2)
        self.assertEqual(data["metadata"]["runs"], 2)

    def test_html_is_escaped(self):
        @function_profile(export_format="html", filename="escaped", log_level="silent")
        def run():
            return "<script>alert(1)</script>"

        run()
        with open("escaped.html") as handle:
            content = handle.read()
        self.assertNotIn("<script>alert(1)</script>", content)
        self.assertIn("&lt;script&gt;", content)

    def test_markdown_pipes_are_escaped(self):
        @function_profile(export_format="md", filename="pipes", log_level="silent")
        def run():
            return "a|b"

        run()
        with open("pipes.md") as handle:
            rows = [line for line in handle if line.startswith("| Return Value")]
        self.assertEqual(len(rows), 1)
        self.assertIn("a\\|b", rows[0])

    def test_invalid_format_fails_at_decoration_time(self):
        with self.assertRaises(ValueError):
            function_profile(export_format="banana")

    def test_invalid_log_level_fails_at_decoration_time(self):
        with self.assertRaises(ValueError):
            function_profile(log_level="verbose")

    def test_invalid_sample_every(self):
        with self.assertRaises(ValueError):
            function_profile(sample_every=0)
        with self.assertRaises(TypeError):
            function_profile(sample_every="2")

    def test_format_is_case_insensitive(self):
        @function_profile(export_format="JSON", filename="upper", log_level="silent")
        def run():
            return 1

        run()
        self.assert_file("upper.json")

    def test_async_function_measures_awaited_lifetime(self):
        @function_profile(export_format="json", filename="async", log_level="silent")
        async def run():
            await asyncio.sleep(0.02)
            return 5

        self.assertEqual(asyncio.run(run()), 5)
        with open("async.json") as handle:
            execution_time = json.load(handle)["profile"]["execution_times"]
        self.assertGreaterEqual(execution_time, 0.015)

    def test_generator_function_measures_consumption(self):
        @function_profile(log_level="silent")
        def generate(n):
            for i in range(n):
                yield i
            return "done"

        self.assertEqual(list(generate(3)), [0, 1, 2])
        stats = next(iter(get_stats().values()))
        self.assertEqual(stats["calls"], 1)
        self.assertGreater(stats["total_time"], 0.0)

    def test_thread_safety(self):
        @function_profile(log_level="silent")
        def run():
            time.sleep(0.001)
            return 1

        threads = [threading.Thread(target=run) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(next(iter(get_stats().values()))["calls"], 8)

    def test_async_generator_warns_instead_of_silently_misreporting(self):
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            @function_profile
            async def stream(n):
                for i in range(n):
                    yield i

        self.assertTrue(any(issubclass(w.category, RuntimeWarning) for w in caught))

        async def collect():
            return [value async for value in stream(3)]

        self.assertEqual(asyncio.run(collect()), [0, 1, 2])
        self.assertEqual(get_stats(), {})

    def test_append_is_rejected_for_structured_formats(self):
        for fmt in ("xml", "yaml", "toml"):
            with self.subTest(fmt=fmt):
                with self.assertRaises(ValueError):
                    function_profile(
                        export_format=fmt, filename="nope", append=True
                    )(lambda: None)()

    def test_shared_log_is_one_file(self):
        @function_profile(shared_log=True, log_level="silent")
        def first():
            return 1

        @function_profile(shared_log=True, log_level="silent")
        def second():
            return 2

        first()
        second()
        logs = glob.glob("func_profiler_logs_*.txt")
        self.assertEqual(len(logs), 1, logs)
        with open(logs[0]) as handle:
            content = handle.read()
        self.assertIn("Profiling log for first", content)
        self.assertIn("Profiling log for second", content)


class TestLineByLineProfile(TempDirTestCase):
    def test_returns_result_and_exports(self):
        decorator = line_by_line_profile(
            export_format="md", filename="lines", log_level="silent"
        )
        profiled = decorator(_sum_squares)
        self.assertEqual(profiled(10), 285)
        self.assert_file("lines.md")
        with open("lines.md") as handle:
            content = handle.read()
        self.assertIn("Line-by-Line Profiling Report: _sum_squares", content)
        self.assertIn("Percent", content)

    def test_bare_decorator(self):
        profiled = line_by_line_profile(_sum_squares)
        self.assertEqual(profiled(4), 14)

    def test_reports_the_profiled_lines(self):
        @line_by_line_profile(log_level="info")
        def run(n):
            total = 0
            for i in range(n):
                total += i
            return total

        run(5)
        output = self.output()
        self.assertIn("Line-by-line profile for 'run'", output)
        self.assertIn("for i in range(n):", output)
        self.assertIn("%", output)

    def test_percentages_sum_to_100(self):
        @line_by_line_profile(
            export_format="json", filename="pct", log_level="silent"
        )
        def run(n):
            total = 0
            for i in range(n):
                total += i * 2
            return total

        run(10)
        with open("pct.json") as handle:
            rows = json.load(handle)["profile"]
        percents = [float(row["Percent"].rstrip("%")) for row in rows]
        self.assertAlmostEqual(sum(percents), 100.0, places=1)

    def test_single_report_for_recursive_calls(self):
        profiled = line_by_line_profile(log_level="info")(_fib)
        self.assertEqual(profiled(6), 8)
        output = self.output()
        self.assertEqual(output.count("Line-by-line profile for '_fib'"), 1)
        self.assertIn("return _fib(n - 1) + _fib(n - 2)", output)

    def test_nested_functions_are_not_traced(self):
        @line_by_line_profile(log_level="info")
        def run(n):
            return _nested_helper_user(n)

        run(4)
        output = self.output()
        self.assertIn("return _nested_helper_user(n)", output)
        self.assertNotIn("return x * x", output)

    def test_restores_previous_trace_function(self):
        events = []

        def debugger(frame, event, arg):
            events.append(event)
            return debugger

        @line_by_line_profile(log_level="silent")
        def run(n):
            return sum(range(n))

        sys.settrace(debugger)
        try:
            run(5)
            self.assertIs(sys.gettrace(), debugger)
        finally:
            sys.settrace(None)
        self.assertTrue(events)

    def test_source_line_numbers_are_accurate(self):
        @line_by_line_profile(
            export_format="json", filename="mapping", log_level="silent"
        )
        def run(n):
            value = n * 2
            return value

        run(3)
        with open("mapping.json") as handle:
            rows = json.load(handle)["profile"]
        source, start = inspect.getsourcelines(run.__wrapped__)
        expected = {
            str(start + index): line.strip()
            for index, line in enumerate(source)
            if line.strip()
        }
        for row in rows:
            self.assertEqual(expected[row["Line Number"]], row["Source Code"])

    def test_exception_cleans_up(self):
        @line_by_line_profile(log_level="silent")
        def boom():
            _raising()

        with self.assertRaises(ValueError):
            boom()
        self.assertIsNone(sys.gettrace())
        self.assertFalse(tracemalloc.is_tracing())
        stats = next(iter(get_stats().values()))
        self.assertEqual(stats["errors"], 1)

    def test_sort_by_time_and_top_n(self):
        @line_by_line_profile(log_level="info", sort_by="time", top_n=2)
        def run(n):
            total = 0
            for i in range(n):
                total += i * i
            time.sleep(0.01)
            return total

        run(20)
        output = self.output()
        self.assertIn("showing 2 of", output)
        lines = output.splitlines()
        header_index = next(
            index for index, line in enumerate(lines) if line.strip().startswith("Line")
        )
        rows = [line for line in lines[header_index + 1 :] if line.startswith("  ")]
        self.assertEqual(len(rows), 2)
        # Sorted by time, the sleep dominates the table.
        self.assertIn("time.sleep(0.01)", rows[0])

    def test_invalid_sort_by(self):
        with self.assertRaises(ValueError):
            line_by_line_profile(sort_by="source")

    def test_exports_all_formats(self):
        for fmt in EXPORT_FORMATS:
            with self.subTest(fmt=fmt):
                profiled = line_by_line_profile(
                    export_format=fmt,
                    filename=f"lbl_{fmt}",
                    log_level="silent",
                )(_sum_squares)
                profiled(5)
                path = self.assert_file(f"lbl_{fmt}.{fmt}")
                if fmt == "json":
                    with open(path) as handle:
                        data = json.load(handle)
                    self.assertEqual(data["metadata"]["profile_type"], "line_by_line_profile")
                    self.assertTrue(data["profile"])
                elif fmt == "xml":
                    ET.parse(path)
                elif fmt == "toml":
                    data = parse_toml(path)
                    if data is not None:
                        self.assertIn("profile", data)
                        self.assertIn("Line Number", data["profile"][0])
                elif fmt == "csv":
                    with open(path) as handle:
                        header = handle.readline()
                    self.assertIn("Source Code", header)
                    self.assertIn("Percent", header)
                elif fmt == "html":
                    with open(path) as handle:
                        self.assertIn("Line-by-Line Profiling Report", handle.read())
                elif fmt == "yaml":
                    with open(path) as handle:
                        content = handle.read()
                    self.assertTrue(content.startswith("-\n"))
                    parsed = parse_yaml(path)
                    if parsed is not None:
                        self.assertTrue(parsed)
                        self.assertIn("Line Number", parsed[0])
                elif fmt == "md":
                    with open(path) as handle:
                        self.assertIn("| Line Number |", handle.read())
                elif fmt == "txt":
                    with open(path) as handle:
                        self.assertIn("Line Number", handle.read())

    def test_append_csv_writes_one_header(self):
        profiled = line_by_line_profile(
            export_format="csv", filename="appended", append=True, log_level="silent"
        )(_sum_squares)
        profiled(2)
        profiled(3)
        with open("appended.csv") as handle:
            rows = handle.read().strip().splitlines()
        self.assertEqual(sum(1 for row in rows if row.startswith("Function Name")), 1)
        self.assertGreater(len(rows), 3)

    def test_append_html_keeps_a_single_document(self):
        profiled = line_by_line_profile(
            export_format="html", filename="htmlruns", append=True, log_level="silent"
        )(_sum_squares)
        profiled(2)
        profiled(3)
        with open("htmlruns.html") as handle:
            content = handle.read()
        self.assertEqual(content.count("</body>"), 1)
        self.assertEqual(content.count("<h2>"), 1)

    def test_no_source_function(self):
        namespace = {}
        exec("def dynamic(x):\n    return x + 1\n", namespace)
        dynamic = line_by_line_profile(
            export_format="json", filename="dynamic", log_level="silent"
        )(namespace["dynamic"])
        self.assertEqual(dynamic(1), 2)
        with open("dynamic.json") as handle:
            rows = json.load(handle)["profile"]
        self.assertEqual(rows[0]["Source Code"], "???")

    def test_memory_can_be_disabled(self):
        @line_by_line_profile(
            log_level="info", track_memory=False, capture_stats=False
        )
        def run(n):
            return sum(range(n))

        run(5)
        self.assertIn("n/a", self.output())
        self.assertFalse(tracemalloc.is_tracing())

    def test_generator_function(self):
        @line_by_line_profile(log_level="info")
        def squares(n):
            for i in range(n):
                yield i * i

        self.assertEqual(list(squares(3)), [0, 1, 4])
        self.assertIn("yield i * i", self.output())

    def test_async_function(self):
        @line_by_line_profile(
            export_format="json", filename="async_lines", log_level="silent"
        )
        async def run(n):
            value = n * 2
            return value

        self.assertEqual(asyncio.run(run(4)), 8)
        with open("async_lines.json") as handle:
            rows = json.load(handle)["profile"]
        self.assertTrue(any("value = n * 2" == row["Source Code"] for row in rows))


class TestProfileBlock(TempDirTestCase):
    def test_measures_block(self):
        with profile_block("load", log_level="silent") as block:
            data = list(range(1000))
        self.assertEqual(len(data), 1000)
        self.assertGreater(block.execution_time, 0.0)
        self.assertIsNotNone(block.peak_memory_usage)
        stats = get_stats()
        self.assertIn("block:load", stats)
        self.assertEqual(stats["block:load"]["calls"], 1)

    def test_export(self):
        with profile_block(
            "exported", export_format="json", filename="block", log_level="silent"
        ):
            time.sleep(0.001)
        with open("block.json") as handle:
            profile = json.load(handle)["profile"]
        self.assertEqual(profile["function_name"], "exported")
        self.assertEqual(profile["profile_type"], "block")

    def test_exception_propagates(self):
        with self.assertRaises(RuntimeError):
            with profile_block("failing", log_level="silent"):
                raise RuntimeError("boom")
        stats = get_stats()["block:failing"]
        self.assertEqual(stats["errors"], 1)
        self.assertFalse(tracemalloc.is_tracing())


class TestStats(TempDirTestCase):
    def test_get_stats_returns_copies(self):
        @function_profile(log_level="silent")
        def run():
            return 1

        run()
        key = stats_key(run)
        stats = get_stats()
        stats[key]["calls"] = 999
        self.assertEqual(get_stats()[key]["calls"], 1)

    def test_reset_stats(self):
        @function_profile(log_level="silent")
        def run():
            return 1

        run()
        self.assertTrue(get_stats())
        reset_stats()
        self.assertEqual(get_stats(), {})

    def test_summary_rows_sorted_by_total_time(self):
        @function_profile(log_level="silent")
        def slow():
            time.sleep(0.005)

        @function_profile(log_level="silent")
        def fast():
            time.sleep(0.001)

        fast()
        slow()
        rows = summary_rows()
        self.assertEqual(rows[0]["Function"], stats_key(slow))
        self.assertEqual(rows[1]["Function"], stats_key(fast))

    def test_top_n(self):
        @function_profile(log_level="silent")
        def first():
            pass

        @function_profile(log_level="silent")
        def second():
            pass

        first()
        second()
        self.assertEqual(len(summary_rows(top_n=1)), 1)

    def test_print_summary(self):
        @function_profile(log_level="silent")
        def run():
            return 1

        run()
        print_summary()
        output = self.output()
        self.assertIn("Profile summary", output)
        self.assertIn(stats_key(run), output)
        self.assertIn("Calls", output)

    def test_print_summary_when_empty(self):
        print_summary()
        self.assertIn("No profiling data", self.output())

    def test_export_summary_when_empty(self):
        path = export_summary("csv", "empty_summary")
        with open(path) as handle:
            header = handle.readline()
        self.assertIn("Function", header)
        self.assertIn("Calls", header)

    def test_profile_summary_alias(self):
        from funcprofiler import profile_summary

        self.assertIs(profile_summary, print_summary)

    def test_export_summary_all_formats(self):
        @function_profile(log_level="silent")
        def run():
            return 1

        run()
        for fmt in EXPORT_FORMATS:
            with self.subTest(fmt=fmt):
                path = export_summary(fmt, f"summary_{fmt}")
                self.assertTrue(os.path.exists(path), path)
                if fmt == "json":
                    with open(path) as handle:
                        data = json.load(handle)
                    self.assertEqual(data["rows"][0]["Function"], stats_key(run))
                elif fmt == "xml":
                    ET.parse(path)
                elif fmt == "toml":
                    data = parse_toml(path)
                    if data is not None:
                        self.assertIn("row", data)
                elif fmt == "csv":
                    with open(path) as handle:
                        self.assertIn("Calls", handle.readline())


class TestUtilities(TempDirTestCase):
    def test_format_duration(self):
        self.assertEqual(format_duration(None), "n/a")
        self.assertEqual(format_duration(0), "0 s")
        self.assertIn("ns", format_duration(1e-9))
        self.assertIn("µs", format_duration(2.5e-6))
        self.assertIn("ms", format_duration(0.002))
        self.assertTrue(format_duration(75).startswith("1m"))
        self.assertTrue(format_duration(3700).startswith("1h"))

    def test_format_memory(self):
        self.assertEqual(format_memory(None), "n/a")
        self.assertIn("kB", format_memory(0.0005))
        self.assertIn("MB", format_memory(0.5))
        self.assertIn("GB", format_memory(2000))

    def test_normalise_format(self):
        self.assertEqual(normalise_format(None), None)
        self.assertEqual(normalise_format("JSON"), "json")
        self.assertEqual(normalise_format("markdown"), "md")
        self.assertEqual(normalise_format(".yml"), "yaml")
        with self.assertRaises(ValueError):
            normalise_format("banana")
        with self.assertRaises(TypeError):
            normalise_format(42)

    def test_export_formats_constant(self):
        self.assertIn("toml", EXPORT_FORMATS)
        self.assertIn("html", EXPORT_FORMATS)

    def test_direct_export_api(self):
        data = {
            "function_name": "manual",
            "execution_times": 0.25,
            "memory_usage": 1.5,
            "peak_memory_usage": 2.5,
        }
        path = export_function_profile_data(data, None, "json", "manual")
        with open(path) as handle:
            self.assertEqual(json.load(handle)["profile"]["function_name"], "manual")

        line_data = {
            "function_name": "manual",
            "line_execution_times": {10: 0.5, 11: 0.5},
            "line_memory_usage": {10: 1.0, 11: 2.0},
        }
        path = export_profiling_data(line_data, _sum_squares, "md", "manual_lines")
        with open(path) as handle:
            content = handle.read()
        self.assertIn("| 10 |", content)
        self.assertIn("50.00%", content)

    def test_shared_log_names_are_stable(self):
        from funcprofiler._utils import shared_log_path

        reset_shared_log_path()
        first = shared_log_path("prefix")
        second = shared_log_path("prefix")
        self.assertEqual(first, second)
        self.assertNotEqual(first, shared_log_path("other"))


class TestPackage(unittest.TestCase):
    def test_public_api(self):
        import funcprofiler

        for name in funcprofiler.__all__:
            self.assertTrue(hasattr(funcprofiler, name), name)
        self.assertRegex(funcprofiler.__version__, r"^\d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main(verbosity=2)
