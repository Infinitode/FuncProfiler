"""Decorators and context managers that collect the profiling data."""

import functools
import inspect
import itertools
import logging
import sys
import threading
import time
import tracemalloc
import warnings

from ._utils import (
    MB,
    append_shared_log,
    format_duration,
    format_memory,
    normalise_format,
    normalise_log_level,
    safe_repr,
    timestamp,
    validate_sample_every,
    validate_sort_by,
    validate_top_n,
)
from .exporters import export_function_profile_data, export_profiling_data
from .stats import record_call

_perf_counter = time.perf_counter
_logger = logging.getLogger("funcprofiler")

_thread_locals = threading.local()


# ---------------------------------------------------------------------------
# Console / log helpers
# ---------------------------------------------------------------------------
def _emit(log_level, logger, level, message):
    """Send ``message`` to ``logger`` or stdout, honouring ``log_level``."""
    if log_level == "silent":
        return
    if level == "debug" and log_level != "debug":
        return
    if logger is not None:
        log_method = getattr(logger, "debug" if level == "debug" else "info", None)
        if log_method is None:  # pragma: no cover - unusual logger objects
            log_method = logger.info
        log_method(message)
    else:
        print(message)


def _record_stats(stats_name, execution_time, peak_memory, memory_usage, error):
    """Record a measurement, never letting a stats failure break user code."""
    try:
        record_call(
            stats_name,
            execution_time,
            peak_memory=peak_memory,
            memory=memory_usage,
            error=error,
        )
    except Exception as exc:  # pragma: no cover - defensive
        _logger.debug("FuncProfiler could not record statistics: %s", exc)


def _warn_unsupported_async_generator(func_name, decorator):
    warnings.warn(
        f"{decorator} cannot profile async generators; '{func_name}' will run "
        "without profiling. Wrap the body in a regular async function instead.",
        RuntimeWarning,
        stacklevel=3,
    )


def _format_arguments(args, kwargs, max_value_length):
    return safe_repr({"args": args, "kwargs": kwargs}, max_value_length)


def _memory_start(track_memory):
    """Begin (or join) memory tracing, returning a session token."""
    if not track_memory:
        return None
    if tracemalloc.is_tracing():
        # Another profiled call (or the application) already owns tracemalloc.
        # Never reset or stop it here: doing so destroyed the outer call's
        # measurements and silently disabled the application's own tracing.
        return (False, tracemalloc.get_traced_memory()[0])
    tracemalloc.start()
    return (True, 0)


def _memory_stop(session):
    """Finish memory tracing and return ``(current_mb, peak_mb)``."""
    if session is None:
        return None, None
    started_here, before = session
    current, peak = tracemalloc.get_traced_memory()
    if started_here:
        tracemalloc.stop()
        return current / MB, peak / MB
    # Nested call: the peak belongs to the outermost profiled call, so only a
    # net allocation delta can be attributed to this call.
    return max(current - before, 0) / MB, None


def _memory_text(value):
    return "n/a" if value is None else f"{value:.12f}MB"


# ---------------------------------------------------------------------------
# Lightweight tracing machinery for line-by-line profiling
# ---------------------------------------------------------------------------
class _TraceRegistry:
    """Per-thread registry of code objects that should be line-traced.

    A single trace function is installed per thread and returns ``None`` for
    frames that are not registered, which keeps the tracing overhead close to
    the cost of the profiled function itself instead of tracing every line of
    every call made by the program.
    """

    __slots__ = ("installed", "previous", "states", "timer", "timers")

    def __init__(self):
        self.states = {}
        self.previous = None
        self.installed = False
        self.timers = {}
        self.timer = time.perf_counter

    def add(self, code, state):
        self.states[code] = state
        if not self.installed:
            self.previous = sys.gettrace()
            sys.settrace(self._global_trace)
            self.installed = True

    def remove(self, code):
        self.states.pop(code, None)
        if not self.states and self.installed:
            sys.settrace(self.previous)
            self.previous = None
            self.installed = False
            self.timers.clear()

    def _global_trace(self, frame, event, arg):
        state = self.states.get(frame.f_code)
        if state is None:
            # Do not trace lines inside unrelated frames (this is the hot path).
            return None
        now = self.timer()
        if event == "call":
            self.timers[frame] = [now, frame.f_lineno]
        return self._local_trace

    def _local_trace(self, frame, event, arg):
        state = self.states.get(frame.f_code)
        if state is None:
            return None
        if event == "line":
            now = self.timer()
            lineno = frame.f_lineno
            entry = self.timers.get(frame)
            if entry is None:
                self.timers[frame] = [now, lineno]
            else:
                start, last = entry
                state.record_line(last, now - start)
                entry[0] = now
                entry[1] = lineno
        elif event == "return":
            entry = self.timers.pop(frame, None)
            if entry is not None:
                state.record_line(entry[1], self.timer() - entry[0])
        return self._local_trace


class _LineState:
    """Accumulated line data for a single profiled call."""

    __slots__ = ("line_memory", "line_times", "track_memory")

    def __init__(self, track_memory):
        self.line_times = {}
        self.line_memory = {}
        self.track_memory = track_memory

    def record_line(self, lineno, elapsed):
        if elapsed < 0:  # pragma: no cover - clock adjustments
            elapsed = 0.0
        self.line_times[lineno] = self.line_times.get(lineno, 0.0) + elapsed
        if self.track_memory and tracemalloc.is_tracing():
            current = tracemalloc.get_traced_memory()[0] / MB
            previous = self.line_memory.get(lineno)
            if previous is None or current > previous:
                self.line_memory[lineno] = current


def _registry():
    registry = getattr(_thread_locals, "registry", None)
    if registry is None:
        registry = _TraceRegistry()
        _thread_locals.registry = registry
    return registry


# ---------------------------------------------------------------------------
# function_profile
# ---------------------------------------------------------------------------
def function_profile(
    export_format=None,
    filename=None,
    shared_log=False,
    enabled=True,
    log_level="info",
    *,
    logger=None,
    capture_stats=True,
    track_memory=True,
    sample_every=1,
    include_args=True,
    include_return_value=True,
    max_value_length=500,
    append=False,
    export_dir=None
):
    """Decorator that profiles the execution time and memory use of a function.

    Parameters:
        export_format (Optional[str]): Export format: ``txt``, ``json``,
            ``csv``, ``html``, ``xml``, ``md``, ``yaml`` or ``toml``
            (case-insensitive). Validated when the decorator is created.
        filename (Optional[str]): Output filename, with or without extension.
        shared_log (bool): Append results to one process-wide log file.
        enabled (bool): When ``False`` the function runs untouched.
        log_level (str): ``"info"``, ``"debug"`` or ``"silent"``.
        logger (Optional[logging.Logger]): Send console output to a logger
            instead of stdout.
        capture_stats (bool): Accumulate the call in :func:`get_stats`.
        track_memory (bool): Measure memory with :mod:`tracemalloc`. Disable to
            cut most of the profiling overhead.
        sample_every (int): Profile only every Nth call (``1`` profiles all).
        include_args (bool): Include the call arguments in logs and exports.
        include_return_value (bool): Include the return value in logs/exports.
        max_value_length (Optional[int]): Truncate reprs to this many chars.
        append (bool): Append to an existing export instead of replacing it.
        export_dir (Optional[str]): Directory for relative export filenames.

    Returns:
        Callable: The profiling decorator (or the wrapped function when used as
        a bare ``@function_profile`` decorator).
    """
    if callable(export_format):
        # Support the bare ``@function_profile`` form.
        target = export_format
        return _wrap_function(
            target,
            fmt=None,
            filename=filename,
            shared_log=shared_log,
            enabled=enabled,
            log_level=normalise_log_level(log_level),
            logger=logger,
            capture_stats=capture_stats,
            track_memory=track_memory,
            sample_every=validate_sample_every(sample_every),
            include_args=include_args,
            include_return_value=include_return_value,
            max_value_length=max_value_length,
            append=append,
            export_dir=export_dir,
        )

    fmt = normalise_format(export_format)
    level = normalise_log_level(log_level)
    sample_every = validate_sample_every(sample_every)

    def decorator(func):
        return _wrap_function(
            func,
            fmt=fmt,
            filename=filename,
            shared_log=shared_log,
            enabled=enabled,
            log_level=level,
            logger=logger,
            capture_stats=capture_stats,
            track_memory=track_memory,
            sample_every=sample_every,
            include_args=include_args,
            include_return_value=include_return_value,
            max_value_length=max_value_length,
            append=append,
            export_dir=export_dir,
        )

    return decorator


def _wrap_function(
    func,
    fmt,
    filename,
    shared_log,
    enabled,
    log_level,
    logger,
    capture_stats,
    track_memory,
    sample_every,
    include_args,
    include_return_value,
    max_value_length,
    append,
    export_dir,
):
    func_name = func.__name__
    module = getattr(func, "__module__", None) or "unknown"
    stats_name = f"{module}.{getattr(func, '__qualname__', func_name)}"
    try:
        filepath = inspect.getfile(func)
    except (TypeError, ValueError):
        filepath = "unknown"
    try:
        line_number = inspect.getsourcelines(func)[1]
    except (OSError, TypeError):
        line_number = 0
    docstring = func.__doc__
    call_counter = itertools.count()

    def skip_call():
        if not enabled:
            return True
        return sample_every > 1 and next(call_counter) % sample_every

    def record(execution_time, memory_usage, peak_memory, error):
        if capture_stats:
            _record_stats(
                stats_name,
                execution_time,
                peak_memory,
                memory_usage,
                error is not None,
            )

    def finish(args, kwargs, result, execution_time, memory_usage, peak_memory):
        arguments = (
            _format_arguments(args, kwargs, max_value_length) if include_args else None
        )
        return_value = (
            safe_repr(result, max_value_length) if include_return_value else None
        )
        _report_function_call(
            func=func,
            func_name=func_name,
            execution_time=execution_time,
            memory_usage=memory_usage,
            peak_memory=peak_memory,
            arguments=arguments,
            return_value=return_value,
            filepath=filepath,
            line_number=line_number,
            docstring=docstring,
            fmt=fmt,
            filename=filename,
            shared_log=shared_log,
            log_level=log_level,
            logger=logger,
            append=append,
            export_dir=export_dir,
        )
        return result

    if inspect.isasyncgenfunction(func):
        _warn_unsupported_async_generator(func_name, "function_profile")
        return func

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if skip_call():
                return await func(*args, **kwargs)
            session = _memory_start(track_memory)
            start = _perf_counter()
            error = None
            try:
                result = await func(*args, **kwargs)
            except BaseException as exc:
                error = exc
                raise
            finally:
                execution_time = _perf_counter() - start
                memory_usage, peak_memory = _memory_stop(session)
                record(execution_time, memory_usage, peak_memory, error)
            return finish(
                args, kwargs, result, execution_time, memory_usage, peak_memory
            )

        return async_wrapper

    if inspect.isgeneratorfunction(func):

        @functools.wraps(func)
        def generator_wrapper(*args, **kwargs):
            if skip_call():
                yield from func(*args, **kwargs)
                return
            session = _memory_start(track_memory)
            start = _perf_counter()
            error = None
            try:
                result = yield from func(*args, **kwargs)
            except BaseException as exc:
                error = exc
                raise
            finally:
                execution_time = _perf_counter() - start
                memory_usage, peak_memory = _memory_stop(session)
                record(execution_time, memory_usage, peak_memory, error)
            return finish(
                args, kwargs, result, execution_time, memory_usage, peak_memory
            )

        return generator_wrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if skip_call():
            return func(*args, **kwargs)
        session = _memory_start(track_memory)
        start = _perf_counter()
        error = None
        try:
            result = func(*args, **kwargs)
        except BaseException as exc:
            error = exc
            raise
        finally:
            execution_time = _perf_counter() - start
            memory_usage, peak_memory = _memory_stop(session)
            record(execution_time, memory_usage, peak_memory, error)
        return finish(args, kwargs, result, execution_time, memory_usage, peak_memory)

    return wrapper


def _report_function_call(
    func,
    func_name,
    execution_time,
    memory_usage,
    peak_memory,
    arguments,
    return_value,
    filepath,
    line_number,
    docstring,
    fmt,
    filename,
    shared_log,
    log_level,
    logger,
    append,
    export_dir,
):
    timestamp_str = timestamp()[2]
    if shared_log:
        lines = [
            f"Profiling log for {func_name}\n",
            f"Date: {timestamp_str[:10]}\n",
            f"Time: {timestamp_str[11:]}\n\n",
        ]
        if arguments is not None:
            lines.append(f"Function {func_name} called with args: {arguments}\n")
        lines.append(
            f"Execution Time: {execution_time:.12f}s, "
            f"Memory usage: {_memory_text(memory_usage)}; "
            f"Peak: {_memory_text(peak_memory)}\n"
        )
        lines.append("-" * 40 + "\n")
        append_shared_log("func_profiler_logs", "".join(lines))

    if fmt:
        profiling_data = {
            "function_name": func_name,
            "execution_times": execution_time,
            "memory_usage": memory_usage,
            "peak_memory_usage": peak_memory,
            "timestamp": timestamp_str,
            "arguments": arguments,
            "return_value": return_value,
            "filepath": filepath,
            "line_number": line_number,
            "docstring": docstring,
        }
        report_name = filename or f"{func_name}_funcprofile_report"
        path = export_function_profile_data(
            profiling_data,
            func,
            fmt,
            report_name,
            append=append,
            export_dir=export_dir,
        )
        _emit(log_level, logger, "info", f"[FUNCPROFILER] Report exported to: {path}")

    if log_level == "debug":
        if arguments is not None:
            _emit(
                log_level,
                logger,
                "debug",
                f"[FUNCPROFILER-DEBUG] Function '{func_name}' called with args: {arguments}",
            )
        _emit(
            log_level,
            logger,
            "debug",
            f"[FUNCPROFILER-DEBUG] Execution Time: {execution_time:.12f}s",
        )
        _emit(
            log_level,
            logger,
            "debug",
            f"[FUNCPROFILER-DEBUG] Memory Usage: {_memory_text(memory_usage)}; "
            f"Peak: {_memory_text(peak_memory)}",
        )
        if return_value is not None:
            _emit(
                log_level,
                logger,
                "debug",
                f"[FUNCPROFILER-DEBUG] Return Value: {return_value}",
            )
    elif log_level == "info":
        _emit(
            log_level,
            logger,
            "info",
            f"[FUNCPROFILER] Function '{func_name}' executed in {execution_time:.12f}s",
        )
        _emit(
            log_level,
            logger,
            "info",
            f"[FUNCPROFILER] Current memory usage: {_memory_text(memory_usage)}; "
            f"Peak: {_memory_text(peak_memory)}",
        )


def line_by_line_profile(
    export_format=None,
    filename=None,
    shared_log=False,
    enabled=True,
    log_level="info",
    *,
    logger=None,
    capture_stats=True,
    track_memory=True,
    sample_every=1,
    include_args=True,
    include_return_value=True,
    max_value_length=500,
    append=False,
    export_dir=None,
    sort_by="line",
    top_n=None
):
    """Decorator for line-by-line profiling of a function.

    Parameters:
        export_format (Optional[str]): Export format (see
            :func:`function_profile`).
        filename (Optional[str]): Output filename, with or without extension.
        shared_log (bool): Append results to one process-wide log file.
        enabled (bool): When ``False`` the function runs untouched.
        log_level (str): ``"info"``, ``"debug"`` or ``"silent"``.
        logger (Optional[logging.Logger]): Send console output to a logger.
        capture_stats (bool): Accumulate the call in :func:`get_stats`.
        track_memory (bool): Sample memory per line with :mod:`tracemalloc`.
        sample_every (int): Profile only every Nth call.
        include_args (bool): Include arguments in logs/exports.
        include_return_value (bool): Include the return value in logs/exports.
        max_value_length (Optional[int]): Truncate reprs to this many chars.
        append (bool): Append to an existing export instead of replacing it.
        export_dir (Optional[str]): Directory for relative export filenames.
        sort_by (str): ``"line"`` (default) or ``"time"`` for the console view.
        top_n (Optional[int]): Only show the N slowest lines in the console.

    Returns:
        Callable: The profiling decorator.
    """
    if callable(export_format):
        target = export_format
        return _wrap_line_function(
            target,
            fmt=None,
            filename=filename,
            shared_log=shared_log,
            enabled=enabled,
            log_level=normalise_log_level(log_level),
            logger=logger,
            capture_stats=capture_stats,
            track_memory=track_memory,
            sample_every=validate_sample_every(sample_every),
            include_args=include_args,
            include_return_value=include_return_value,
            max_value_length=max_value_length,
            append=append,
            export_dir=export_dir,
            sort_by=validate_sort_by(sort_by, ("line", "time")),
            top_n=validate_top_n(top_n),
        )

    fmt = normalise_format(export_format)
    level = normalise_log_level(log_level)
    sample_every = validate_sample_every(sample_every)
    sort_by = validate_sort_by(sort_by, ("line", "time"))
    top_n = validate_top_n(top_n)

    def decorator(func):
        return _wrap_line_function(
            func,
            fmt=fmt,
            filename=filename,
            shared_log=shared_log,
            enabled=enabled,
            log_level=level,
            logger=logger,
            capture_stats=capture_stats,
            track_memory=track_memory,
            sample_every=sample_every,
            include_args=include_args,
            include_return_value=include_return_value,
            max_value_length=max_value_length,
            append=append,
            export_dir=export_dir,
            sort_by=sort_by,
            top_n=top_n,
        )

    return decorator


def _wrap_line_function(
    func,
    fmt,
    filename,
    shared_log,
    enabled,
    log_level,
    logger,
    capture_stats,
    track_memory,
    sample_every,
    include_args,
    include_return_value,
    max_value_length,
    append,
    export_dir,
    sort_by,
    top_n,
):
    func_name = func.__name__
    module = getattr(func, "__module__", None) or "unknown"
    stats_name = f"{module}.{getattr(func, '__qualname__', func_name)}"
    target_code = func.__code__
    try:
        filepath = inspect.getfile(func)
    except (TypeError, ValueError):
        filepath = "unknown"
    try:
        source_lines, starting_line = inspect.getsourcelines(func)
    except (OSError, TypeError):
        source_lines, starting_line = [], 0
    docstring = func.__doc__
    call_counter = itertools.count()

    def skip_call():
        if not enabled:
            return True
        return sample_every > 1 and next(call_counter) % sample_every

    def active():
        return target_code in _registry().states

    def begin():
        state = _LineState(track_memory)
        session = _memory_start(track_memory)
        start = _perf_counter()
        registry = _registry()
        registry.add(target_code, state)
        return state, session, start, registry

    def end(session, start, registry, error):
        execution_time = _perf_counter() - start
        registry.remove(target_code)
        memory_usage, peak_memory = _memory_stop(session)
        if capture_stats:
            _record_stats(
                stats_name,
                execution_time,
                peak_memory,
                memory_usage,
                error is not None,
            )
        return execution_time, memory_usage, peak_memory

    def finish(args, kwargs, result, state, execution_time, peak_memory):
        arguments = (
            _format_arguments(args, kwargs, max_value_length) if include_args else None
        )
        return_value = (
            safe_repr(result, max_value_length) if include_return_value else None
        )
        _report_line_profile(
            func=func,
            func_name=func_name,
            state=state,
            source_lines=source_lines,
            starting_line=starting_line,
            execution_time=execution_time,
            peak_memory=peak_memory,
            arguments=arguments,
            return_value=return_value,
            filepath=filepath,
            docstring=docstring,
            fmt=fmt,
            filename=filename,
            shared_log=shared_log,
            log_level=log_level,
            logger=logger,
            append=append,
            export_dir=export_dir,
            sort_by=sort_by,
            top_n=top_n,
        )
        return result

    if inspect.isasyncgenfunction(func):
        _warn_unsupported_async_generator(func_name, "line_by_line_profile")
        return func

    if inspect.iscoroutinefunction(func):
        # Async functions are profiled across the whole awaited lifetime; time
        # spent suspended at an ``await`` is not attributed to any line.
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if skip_call() or active():
                return await func(*args, **kwargs)
            state, session, start, registry = begin()
            error = None
            try:
                result = await func(*args, **kwargs)
            except BaseException as exc:
                error = exc
                raise
            finally:
                execution_time, _, peak_memory = end(session, start, registry, error)
            return finish(args, kwargs, result, state, execution_time, peak_memory)

        return async_wrapper

    if inspect.isgeneratorfunction(func):
        # Generators are profiled from the first ``next()`` to exhaustion.
        @functools.wraps(func)
        def generator_wrapper(*args, **kwargs):
            if skip_call() or active():
                yield from func(*args, **kwargs)
                return
            state, session, start, registry = begin()
            error = None
            try:
                result = yield from func(*args, **kwargs)
            except BaseException as exc:
                error = exc
                raise
            finally:
                execution_time, _, peak_memory = end(session, start, registry, error)
            return finish(args, kwargs, result, state, execution_time, peak_memory)

        return generator_wrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if skip_call():
            return func(*args, **kwargs)
        if active():
            # Recursive re-entry: keep the outer profile in charge and let the
            # inner time be attributed to the calling line.
            return func(*args, **kwargs)
        state, session, start, registry = begin()
        error = None
        try:
            result = func(*args, **kwargs)
        except BaseException as exc:
            error = exc
            raise
        finally:
            execution_time, _, peak_memory = end(session, start, registry, error)
        return finish(args, kwargs, result, state, execution_time, peak_memory)

    return wrapper

def _source_for(source_lines, starting_line, lineno):
    index = lineno - starting_line
    if source_lines and 0 <= index < len(source_lines):
        return source_lines[index].strip()
    return "???"


def _report_line_profile(
    func,
    func_name,
    state,
    source_lines,
    starting_line,
    execution_time,
    peak_memory,
    arguments,
    return_value,
    filepath,
    docstring,
    fmt,
    filename,
    shared_log,
    log_level,
    logger,
    append,
    export_dir,
    sort_by,
    top_n,
):
    line_times = state.line_times
    line_memory = state.line_memory
    total = sum(line_times.values())

    ordered = sorted(line_times.items())
    if sort_by == "time":
        ordered.sort(key=lambda item: (-item[1], item[0]))
    shown = ordered[:top_n] if top_n is not None else ordered

    if log_level != "silent":
        header = (
            f"[FUNCPROFILER] Line-by-line profile for '{func_name}' "
            f"({len(line_times)} line(s), total {format_duration(total)}, "
            f"peak {format_memory(peak_memory)})"
        )
        if top_n is not None and len(ordered) > top_n:
            header += f" - showing {top_n} of {len(ordered)} lines"
        _emit(log_level, logger, "info", header)

        rows = []
        for lineno, seconds in shown:
            source = _source_for(source_lines, starting_line, lineno)
            if len(source) > 70:
                source = source[:67] + "..."
            percent = (seconds / total * 100.0) if total else 0.0
            rows.append(
                (
                    str(lineno),
                    source,
                    format_duration(seconds),
                    f"{percent:.2f}%",
                    format_memory(line_memory.get(lineno)),
                )
            )
        headers = ("Line", "Source", "Time", "%", "Memory")
        widths = [
            max([len(headers[i])] + [len(row[i]) for row in rows])
            for i in range(len(headers))
        ]
        prefix = "  "
        _emit(
            log_level,
            logger,
            "info",
            prefix
            + "  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))).rstrip(),
        )
        for row in rows:
            _emit(
                log_level,
                logger,
                "info",
                prefix
                + "  ".join(row[i].ljust(widths[i]) for i in range(len(headers))).rstrip(),
            )

        if log_level == "debug":
            if arguments is not None:
                _emit(
                    log_level,
                    logger,
                    "debug",
                    f"[FUNCPROFILER-DEBUG] Called with args: {arguments}",
                )
            _emit(
                log_level,
                logger,
                "debug",
                f"[FUNCPROFILER-DEBUG] Total execution time: {execution_time:.12f}s",
            )
            if return_value is not None:
                _emit(
                    log_level,
                    logger,
                    "debug",
                    f"[FUNCPROFILER-DEBUG] Return Value: {return_value}",
                )

    if shared_log:
        lines = [
            f"Profiling log for {func_name}\n",
            f"Date: {timestamp()[0]}\n",
            f"Time: {timestamp()[1]}\n\n",
        ]
        for lineno, seconds in sorted(line_times.items()):
            source = _source_for(source_lines, starting_line, lineno)
            lines.append(
                f"Line {lineno} ({source}): Execution Time: {seconds:.12f}s, "
                f"Memory Usage: {_memory_text(line_memory.get(lineno))}\n"
            )
        lines.append("\n" + "-" * 40 + "\n\n")
        append_shared_log("lbl_profiler_logs", "".join(lines))

    if fmt:
        profiling_data = {
            "function_name": func_name,
            "timestamp": timestamp()[2],
            "arguments": arguments,
            "return_value": return_value,
            "filepath": filepath,
            "docstring": docstring,
            "peak_memory_usage": peak_memory,
            "line_execution_times": line_times,
            "line_memory_usage": line_memory,
        }
        report_name = filename or f"{func_name}_lblprofile_report"
        path = export_profiling_data(
            profiling_data,
            func,
            fmt,
            report_name,
            append=append,
            export_dir=export_dir,
            source_lines=source_lines,
            starting_line=starting_line,
        )
        _emit(log_level, logger, "info", f"[FUNCPROFILER] Report exported to: {path}")


# ---------------------------------------------------------------------------
# profile_block
# ---------------------------------------------------------------------------
class ProfileBlock:
    """Context manager returned by :func:`profile_block`."""

    def __init__(
        self,
        name="block",
        export_format=None,
        filename=None,
        shared_log=False,
        log_level="info",
        logger=None,
        capture_stats=True,
        track_memory=True,
        append=False,
        export_dir=None,
    ):
        self.name = name
        self.export_format = normalise_format(export_format)
        self.filename = filename
        self.shared_log = shared_log
        self.log_level = normalise_log_level(log_level)
        self.logger = logger
        self.capture_stats = capture_stats
        self.track_memory = track_memory
        self.append = append
        self.export_dir = export_dir

        self.execution_time = None
        self.memory_usage = None
        self.peak_memory_usage = None
        self.error = None
        self._session = None
        self._start = None

    def __enter__(self):
        self._session = _memory_start(self.track_memory)
        self._start = _perf_counter()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.execution_time = _perf_counter() - self._start
        self.memory_usage, self.peak_memory_usage = _memory_stop(self._session)
        self.error = exc

        if self.capture_stats:
            _record_stats(
                f"block:{self.name}",
                self.execution_time,
                self.peak_memory_usage,
                self.memory_usage,
                exc is not None,
            )

        if exc_type is None:
            self._report()
        else:
            _emit(
                self.log_level,
                self.logger,
                "debug",
                f"[FUNCPROFILER-DEBUG] Block '{self.name}' raised "
                f"{exc_type.__name__}: {exc}",
            )
        return False

    def _report(self):
        timestamp_str = timestamp()[2]
        if self.shared_log:
            lines = [
                f"Profiling log for block {self.name}\n",
                f"Date: {timestamp_str[:10]}\n",
                f"Time: {timestamp_str[11:]}\n\n",
                (
                    f"Execution Time: {self.execution_time:.12f}s, "
                    f"Memory usage: {_memory_text(self.memory_usage)}; "
                    f"Peak: {_memory_text(self.peak_memory_usage)}\n"
                ),
                "-" * 40 + "\n",
            ]
            append_shared_log("func_profiler_logs", "".join(lines))

        if self.export_format:
            profiling_data = {
                "function_name": self.name,
                "profile_type": "block",
                "execution_times": self.execution_time,
                "memory_usage": self.memory_usage,
                "peak_memory_usage": self.peak_memory_usage,
                "timestamp": timestamp_str,
            }
            report_name = self.filename or f"{self.name}_block_report"
            path = export_function_profile_data(
                profiling_data,
                None,
                self.export_format,
                report_name,
                append=self.append,
                export_dir=self.export_dir,
            )
            _emit(
                self.log_level,
                self.logger,
                "info",
                f"[FUNCPROFILER] Report exported to: {path}",
            )

        _emit(
            self.log_level,
            self.logger,
            "info",
            f"[FUNCPROFILER] Block '{self.name}' executed in "
            f"{self.execution_time:.12f}s",
        )
        _emit(
            self.log_level,
            self.logger,
            "info",
            f"[FUNCPROFILER] Block '{self.name}' memory usage: "
            f"{_memory_text(self.memory_usage)}; Peak: "
            f"{_memory_text(self.peak_memory_usage)}",
        )


def profile_block(
    name="block",
    export_format=None,
    filename=None,
    shared_log=False,
    log_level="info",
    *,
    logger=None,
    capture_stats=True,
    track_memory=True,
    append=False,
    export_dir=None
):
    """Profile an arbitrary ``with`` block instead of a function.

    Example::

        with profile_block("load-data", log_level="silent") as block:
            rows = load()
        print(block.execution_time, block.peak_memory_usage)

    Parameters mirror :func:`function_profile`.
    """
    return ProfileBlock(
        name=name,
        export_format=export_format,
        filename=filename,
        shared_log=shared_log,
        log_level=log_level,
        logger=logger,
        capture_stats=capture_stats,
        track_memory=track_memory,
        append=append,
        export_dir=export_dir,
    )


__all__ = ["ProfileBlock", "function_profile", "line_by_line_profile", "profile_block"]
