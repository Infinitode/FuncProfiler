"""Internal helpers shared by the FuncProfiler modules.

Nothing in this module is part of the public API, but the helpers are kept
small, dependency-free and Python 3.8 compatible.
"""

import html
import json
import math
import os
import threading
import time

#: Every export format understood by the library.
VALID_FORMATS = ("txt", "json", "csv", "html", "xml", "md", "yaml", "toml")

_FORMAT_ALIASES = {
    "text": "txt",
    "htm": "html",
    "markdown": "md",
    "yml": "yaml",
}

#: Valid values for the ``log_level`` option.
LOG_LEVELS = ("info", "debug", "silent")

_LOG_LEVEL_ALIASES = {
    "none": "silent",
    "off": "silent",
    "quiet": "silent",
    "warn": "silent",
    "warning": "silent",
    "error": "silent",
}

MB = 10 ** 6

_shared_log_lock = threading.Lock()
_shared_log_paths = {}


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------
def normalise_format(export_format, allow_none=True):
    """Return the canonical export format name, validating it eagerly.

    Accepting aliases and mixed case here means a typo such as
    ``export_format="Markdown"`` works, while ``export_format="banana"`` fails
    at decoration time instead of after the profiled function has already run.
    """
    if export_format is None:
        if allow_none:
            return None
        raise ValueError("An export format is required for this operation.")
    if not isinstance(export_format, str):
        raise TypeError(
            "export_format must be a string, got "
            f"{type(export_format).__name__!r}."
        )
    fmt = export_format.strip().lower()
    if fmt.startswith("."):
        fmt = fmt[1:]
    fmt = _FORMAT_ALIASES.get(fmt, fmt)
    if fmt not in VALID_FORMATS:
        raise ValueError(
            f"Unsupported export format {export_format!r}. "
            f"Choose one of: {', '.join(VALID_FORMATS)}."
        )
    return fmt


def normalise_log_level(log_level):
    """Return one of ``info``, ``debug`` or ``silent``."""
    if log_level is None:
        return "silent"
    if not isinstance(log_level, str):
        raise TypeError(
            f"log_level must be a string, got {type(log_level).__name__!r}."
        )
    level = log_level.strip().lower()
    level = _LOG_LEVEL_ALIASES.get(level, level)
    if level not in LOG_LEVELS:
        raise ValueError(
            f"Unsupported log_level {log_level!r}. "
            f"Choose one of: {', '.join(LOG_LEVELS)}."
        )
    return level


def validate_sample_every(sample_every):
    """Validate the ``sample_every`` option and return it as an int."""
    if isinstance(sample_every, bool) or not isinstance(sample_every, int):
        raise TypeError("sample_every must be an integer greater than or equal to 1.")
    if sample_every < 1:
        raise ValueError("sample_every must be greater than or equal to 1.")
    return sample_every


def validate_top_n(top_n):
    """Validate the ``top_n`` option (``None`` means "show everything")."""
    if top_n is None:
        return None
    if isinstance(top_n, bool) or not isinstance(top_n, int):
        raise TypeError("top_n must be an integer or None.")
    if top_n < 1:
        raise ValueError("top_n must be greater than or equal to 1.")
    return top_n


def validate_sort_by(sort_by, allowed):
    """Validate ``sort_by`` against ``allowed`` and return its lower-case form."""
    if not isinstance(sort_by, str):
        raise TypeError("sort_by must be a string.")
    value = sort_by.strip().lower()
    if value not in allowed:
        raise ValueError(
            f"Unsupported sort_by {sort_by!r}. Choose one of: {', '.join(allowed)}."
        )
    return value


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def format_duration(seconds):
    """Format a duration in seconds using a readable unit (ns, µs, ms, s, m)."""
    if seconds is None:
        return "n/a"
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return str(seconds)

    sign = "-" if seconds < 0 else ""
    value = abs(seconds)
    if value == 0:
        return "0 s"
    if value < 1e-6:
        return f"{sign}{value * 1e9:.2f} ns"
    if value < 1e-3:
        return f"{sign}{value * 1e6:.2f} µs"
    if value < 1.0:
        return f"{sign}{value * 1e3:.3f} ms"
    if value < 60.0:
        return f"{sign}{value:.6g} s"
    minutes, secs = divmod(value, 60.0)
    if minutes < 60:
        return f"{sign}{int(minutes)}m {secs:.2f}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{sign}{hours}h {minutes}m {secs:.2f}s"


def format_memory(megabytes):
    """Format a size expressed in megabytes using a readable unit."""
    if megabytes is None:
        return "n/a"
    try:
        megabytes = float(megabytes)
    except (TypeError, ValueError):
        return str(megabytes)
    if megabytes < 1e-3:
        return f"{megabytes * 1e3:.4f} kB"
    if megabytes < 1e3:
        return f"{megabytes:.4f} MB"
    return f"{megabytes / 1e3:.4f} GB"


def safe_repr(value, max_length=500):
    """Return ``repr(value)`` without ever raising, truncated to ``max_length``."""
    try:
        text = repr(value)
    except Exception:  # pragma: no cover - defensive, user objects can be hostile
        text = f"<unrepresentable {type(value).__name__}>"
    if max_length is not None and len(text) > max_length:
        head = text[: max_length - 3] + "..."
        # Keep reprs of strings/containers balanced when truncating.
        if len(text) > 1 and text[0] in "'\"" and text[-1] == text[0]:
            head = text[: max_length - 4] + "..." + text[0]
        text = head
    return text


def display_value(value):
    """Render a value for tabular exports (``None`` becomes an empty cell)."""
    if value is None:
        return ""
    if isinstance(value, float):
        # Keep the full precision the profiler produced but drop the
        # floating point noise of ``str()`` for typical timings.
        return repr(value)
    return str(value)


def escape_md(value):
    """Escape a value so it is safe inside a Markdown table cell."""
    text = display_value(value)
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def escape_md_code(value):
    """Escape a value for a Markdown inline code span."""
    text = (
        display_value(value)
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("|", "\\|")
    )
    if "`" in text:
        return f"`` {text} ``"
    return f"`{text}`"


def escape_html(value):
    """Escape a value for HTML text content (quotes included)."""
    return html.escape(display_value(value), quote=True)


# ---------------------------------------------------------------------------
# Serialisation helpers for the YAML and TOML exporters
# ---------------------------------------------------------------------------
def yaml_key(key):
    """Return a YAML mapping key, quoting it when it is not plain-safe."""
    text = str(key)
    if text and all(ch.isalnum() or ch in "_-." for ch in text):
        return text
    return json.dumps(text, ensure_ascii=False)


def yaml_scalar(value):
    """Serialise a scalar as a valid YAML scalar."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return ".nan"
        if math.isinf(value):
            return ".inf" if value > 0 else "-.inf"
        return repr(value)
    # JSON double-quoted strings are valid YAML double-quoted scalars and
    # correctly escape quotes, backslashes and control characters.
    return json.dumps(str(value), ensure_ascii=False)


def yaml_mapping_lines(data, indent=0):
    """Render a flat mapping as YAML lines, using block scalars for text."""
    pad = " " * indent
    lines = []
    for key, value in data.items():
        name = yaml_key(key)
        if isinstance(value, str) and "\n" in value:
            # ``|-`` keeps the value without adding a trailing newline.
            lines.append(f"{pad}{name}: |-")
            for line in value.replace("\r\n", "\n").rstrip("\n").split("\n"):
                lines.append(f"{pad}  {line}" if line else f"{pad}")
        else:
            lines.append(f"{pad}{name}: {yaml_scalar(value)}")
    return lines


def toml_key(key):
    """Return a TOML key, quoting it when it is not a bare key."""
    text = str(key)
    if text and all(ch.isalnum() or ch in "_-" for ch in text):
        return text
    return json.dumps(text, ensure_ascii=False)


def toml_scalar(value):
    """Serialise a scalar as a valid TOML value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    if value is None:
        # TOML has no null literal; an empty string is the least surprising
        # representation and keeps round-trips parseable.
        return '""'
    # JSON strings use the same escaping rules as TOML basic strings.
    return json.dumps(str(value), ensure_ascii=False)


def toml_mapping_lines(data, indent=0):
    """Render a flat mapping as TOML key/value pairs."""
    pad = " " * indent
    return [f"{pad}{toml_key(key)} = {toml_scalar(value)}" for key, value in data.items()]


# ---------------------------------------------------------------------------
# File handling
# ---------------------------------------------------------------------------
def resolve_path(filename, export_format, export_dir=None):
    """Build the output path for ``filename`` without doubling the extension.

    ``filename="report.json"`` with ``export_format="json"`` now produces
    ``report.json`` rather than ``report.json.json``. Missing parent
    directories are created so exports into a ``reports/`` folder just work.
    """
    if filename is None:
        raise ValueError("A filename is required to export profiling data.")
    path = os.fspath(filename)
    if export_dir and not os.path.isabs(path):
        path = os.path.join(os.fspath(export_dir), path)
    suffix = "." + export_format
    if not path.lower().endswith(suffix):
        path += suffix
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


# ---------------------------------------------------------------------------
# Shared log file handling
# ---------------------------------------------------------------------------
def shared_log_path(prefix):
    """Return the process-wide shared log path for ``prefix``.

    The previous implementation derived the file name from the clock at
    *decoration* time, so two functions decorated in different seconds ended
    up in different files even though ``shared_log=True`` promises a single
    shared log. The name is now resolved once per process (and per profiler
    flavour) on first use.
    """
    path = _shared_log_paths.get(prefix)
    if path is None:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = f"{prefix}_{stamp}.txt"
        _shared_log_paths[prefix] = path
    return path


def reset_shared_log_path():
    """Forget the cached shared-log name (used by tests)."""
    with _shared_log_lock:
        _shared_log_paths.clear()


def append_shared_log(prefix, text):
    """Append ``text`` to the shared log, serialising writes across threads."""
    path = shared_log_path(prefix)
    with _shared_log_lock, open(path, "a", encoding="utf-8") as handle:
        handle.write(text)
    return path


def timestamp():
    """Return ``(date, time, full)`` for the current local time."""
    now = time.localtime()
    full = time.strftime("%Y-%m-%d %H:%M:%S", now)
    return full[:10], full[11:], full
