"""Export helpers for FuncProfiler reports.

The exporters are deliberately free of side effects on stdout: the decorators
decide what to report and when. Every function returns the path it wrote so
callers can log or assert against it.
"""

import csv
import io
import json
import os
import re
import xml.etree.ElementTree as ET

from ._utils import (
    display_value,
    escape_html,
    escape_md,
    escape_md_code,
    normalise_format,
    read_text,
    resolve_path,
    timestamp,
    toml_key,
    toml_mapping_lines,
    toml_scalar,
    write_text,
    yaml_key,
    yaml_mapping_lines,
    yaml_scalar,
)

_FORMAT_DESCRIPTION = "txt, json, csv, html, xml, md, yaml or toml"
_CODE_COLUMNS = ("Source Code",)

_HTML_STYLE = """\
    :root { color-scheme: light dark; }
    body { font-family: system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
           margin: 2rem auto; max-width: 72rem; padding: 0 1rem; line-height: 1.45; }
    h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
    h2 { font-size: 1.1rem; margin-top: 2rem; }
    p.meta { color: #6b7280; margin-top: 0; font-size: 0.85rem; }
    table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.9rem; }
    th, td { border: 1px solid #d1d5db; text-align: left; padding: 0.4rem 0.6rem;
             vertical-align: top; }
    th { background: #f3f4f6; position: sticky; top: 0; }
    tbody tr:nth-child(even) { background: rgba(127, 127, 127, 0.06); }
    td.code, code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
                    white-space: pre-wrap; }
    .section + .section { border-top: 1px dashed #d1d5db; }
"""

_XML_INVALID = re.compile(r"[^A-Za-z0-9_.-]+")


def _reject_append(fmt, append):
    """Appending is only meaningful for formats that can hold multiple runs."""
    if append and fmt in ("xml", "yaml", "toml"):
        raise ValueError(
            f"append=True is not supported for {fmt!r} exports; "
            "use txt, json, csv, md or html, or export to a new file."
        )


def _xml_tag(key):
    """Turn a column name into a valid XML element name."""
    tag = _XML_INVALID.sub("_", str(key)).strip("_")
    if not tag:
        tag = "Field"
    if tag[0].isdigit():
        tag = "Field_" + tag
    return tag


def _headers_for(rows):
    headers = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    return headers


# ---------------------------------------------------------------------------
# Tabular renderers
# ---------------------------------------------------------------------------
def _txt_table(headers, rows):
    cells = [
        [
            display_value(row.get(h)).replace("\r", " ").replace("\n", " ")
            for h in headers
        ]
        for row in rows
    ]
    widths = [
        max([len(str(h))] + [len(cell[i]) for cell in cells])
        for i, h in enumerate(headers)
    ]
    lines = [
        "  ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)).rstrip(),
        "  ".join("-" * widths[i] for i in range(len(headers))),
    ]
    for cell in cells:
        lines.append(
            "  ".join(cell[i].ljust(widths[i]) for i in range(len(headers))).rstrip()
        )
    return "\n".join(lines) + "\n"


def _csv_table(headers, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=headers, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({h: display_value(row.get(h)) for h in headers})
    return buffer.getvalue()


def _md_table(headers, rows):
    lines = [
        "| " + " | ".join(escape_md(h) for h in headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        cells = []
        for header in headers:
            value = row.get(header)
            if header in _CODE_COLUMNS:
                cells.append(escape_md_code(value))
            else:
                cells.append(escape_md(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _html_table(headers, rows):
    parts = ["<table>", "<thead><tr>"]
    for header in headers:
        parts.append(f"<th>{escape_html(header)}</th>")
    parts.append("</tr></thead>")
    parts.append("<tbody>")
    for row in rows:
        parts.append("<tr>")
        for header in headers:
            css = ' class="code"' if header in _CODE_COLUMNS else ""
            parts.append(f"<td{css}>{escape_html(row.get(header))}</td>")
        parts.append("</tr>")
    parts.append("</tbody>")
    parts.append("</table>")
    return "\n".join(parts)


def _html_document(title, body, generated_at):
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape_html(title)}</title>\n<style>\n{_HTML_STYLE}</style>\n"
        "</head>\n<body>\n"
        f"<h1>{escape_html(title)}</h1>\n"
        f'<p class="meta">Generated by FuncProfiler on {escape_html(generated_at)}</p>\n'
        f"{body}\n</body>\n</html>\n"
    )


def _append_html_section(path, title, table_html, generated_at):
    section = (
        '<section class="section">\n'
        f"<h2>{escape_html(title)}</h2>\n"
        f'<p class="meta">Run at {escape_html(generated_at)}</p>\n'
        f"{table_html}\n</section>"
    )
    try:
        document = read_text(path)
    except OSError:
        document = ""
    if "</body>" in document:
        document = document.replace("</body>", section + "\n</body>", 1)
    else:
        document = _html_document(title, section, generated_at)
    write_text(path, document)


def _write_tabular(headers, rows, export_format, path, title, append, generated_at):
    """Write ``txt``/``csv``/``md``/``html`` reports and return the path."""
    if export_format == "txt":
        text = f"{title}\nGenerated: {generated_at}\n\n" + _txt_table(headers, rows)
        if append and os.path.exists(path):
            text = "\n" + ("-" * 70) + f"\n{title} (run at {generated_at})\n\n" + _txt_table(
                headers, rows
            )
            with open(path, "a", encoding="utf-8", newline="") as handle:
                handle.write(text)
        else:
            write_text(path, text)

    elif export_format == "csv":
        if append and os.path.exists(path) and os.path.getsize(path) > 0:
            buffer = io.StringIO()
            writer = csv.DictWriter(
                buffer, fieldnames=headers, extrasaction="ignore", lineterminator="\n"
            )
            for row in rows:
                writer.writerow({h: display_value(row.get(h)) for h in headers})
            with open(path, "a", encoding="utf-8", newline="") as handle:
                handle.write(buffer.getvalue())
        else:
            write_text(path, _csv_table(headers, rows))

    elif export_format == "md":
        table = _md_table(headers, rows)
        if append and os.path.exists(path):
            with open(path, "a", encoding="utf-8", newline="") as handle:
                handle.write(
                    f"\n## {title} (run at {generated_at})\n\n{table}\n"
                )
        else:
            write_text(path, f"# {title}\n\n{table}\n")

    elif export_format == "html":
        table = _html_table(headers, rows)
        if append and os.path.exists(path):
            _append_html_section(path, title, table, generated_at)
        else:
            body = (
                '<section class="section">\n'
                f'<p class="meta">Rows: {len(rows)}</p>\n{table}\n</section>'
            )
            write_text(path, _html_document(title, body, generated_at))

    else:  # pragma: no cover - guarded by normalise_format
        raise ValueError(
            f"Unsupported tabular export format {export_format!r}; "
            f"use {_FORMAT_DESCRIPTION}."
        )
    return path


# ---------------------------------------------------------------------------
# Function profile exports
# ---------------------------------------------------------------------------
def _pretty_key(key):
    return str(key).replace("_", " ").title()


def _json_with_runs(profile_type, profile, path, append):
    """Build a JSON payload, growing ``runs`` when appending to an existing file."""
    if append and os.path.exists(path):
        try:
            existing = json.loads(read_text(path))
        except (OSError, ValueError):
            existing = None
        if isinstance(existing, dict):
            runs = existing.get("runs")
            if not isinstance(runs, list):
                runs = []
                if "profile" in existing:
                    runs.append(existing["profile"])
                elif existing:
                    runs.append(existing)
            runs.append(profile)
            return {
                "metadata": {
                    "profile_type": profile_type,
                    "export_time": timestamp()[2],
                    "runs": len(runs),
                },
                "runs": runs,
            }
    return {
        "metadata": {"profile_type": profile_type, "export_time": timestamp()[2]},
        "profile": profile,
    }


def export_function_profile_data(
    profiling_data, func, export_format, filename, append=False, export_dir=None
):
    """Export function-level profiling data and return the written path.

    Parameters:
        profiling_data (dict): The metrics collected for the call.
        func (Callable): The profiled function (may be ``None`` for blocks).
        export_format (str): One of ``txt``, ``json``, ``csv``, ``html``,
            ``xml``, ``md``, ``yaml`` or ``toml`` (case-insensitive).
        filename (str): Output filename, with or without the extension.
        append (bool): Append to an existing report instead of replacing it.
            Supported for ``txt``, ``json``, ``csv``, ``md`` and ``html``.
        export_dir (Optional[str]): Directory used to resolve relative
            ``filename`` values.
    """
    fmt = normalise_format(export_format, allow_none=False)
    _reject_append(fmt, append)
    path = resolve_path(filename, fmt, export_dir=export_dir)
    generated_at = timestamp()[2]
    title = f"Function Profiling Report: {profiling_data.get('function_name', 'unknown')}"

    if fmt in ("txt", "csv", "md", "html"):
        if fmt == "csv":
            headers = list(profiling_data.keys())
            rows = [profiling_data]
        else:
            headers = ["Metric", "Value"]
            rows = [
                {"Metric": _pretty_key(key), "Value": display_value(value)}
                for key, value in profiling_data.items()
            ]
        return _write_tabular(
            headers, rows, fmt, path, title, append, generated_at
        )

    if fmt == "json":
        payload = _json_with_runs("function_profile", profiling_data, path, append)
        write_text(path, json.dumps(payload, indent=4, default=str) + "\n")
        return path

    if fmt == "xml":
        root = ET.Element("FunctionProfile")
        for key, value in profiling_data.items():
            ET.SubElement(root, _xml_tag(_pretty_key(key))).text = display_value(value)
        ET.ElementTree(root).write(
            path, encoding="utf-8", xml_declaration=True
        )
        return path

    if fmt == "yaml":
        write_text(path, "\n".join(yaml_mapping_lines(profiling_data)) + "\n")
        return path

    if fmt == "toml":
        write_text(path, "\n".join(toml_mapping_lines(profiling_data)) + "\n")
        return path

    raise ValueError(  # pragma: no cover - normalise_format rejects these
        f"Unsupported export format {export_format!r}; use {_FORMAT_DESCRIPTION}."
    )


# ---------------------------------------------------------------------------
# Line-by-line exports
# ---------------------------------------------------------------------------
def _line_rows(profiling_data, func, source_lines, starting_line):
    line_times = profiling_data.get("line_execution_times") or {}
    line_memory = profiling_data.get("line_memory_usage") or {}
    name = profiling_data.get("function_name") or getattr(func, "__name__", "unknown")
    run_timestamp = profiling_data.get("timestamp") or timestamp()[2]
    total = sum(line_times.values())

    rows = []
    for line_no in sorted(line_times):
        index = int(line_no) - int(starting_line or 0)
        if source_lines and 0 <= index < len(source_lines):
            source = source_lines[index].strip()
        else:
            source = "???"
        seconds = line_times[line_no]
        percent = (seconds / total * 100.0) if total else 0.0
        memory = line_memory.get(line_no)
        rows.append(
            {
                "Function Name": name,
                "Line Number": str(line_no),
                "Source Code": source,
                "Execution Time (s)": f"{seconds:.12f}",
                "Percent": f"{percent:.2f}%",
                "Memory Usage (MB)": "" if memory is None else f"{memory:.12f}",
                "Timestamp": run_timestamp,
            }
        )
    return rows


def export_profiling_data(
    profiling_data,
    func,
    export_format,
    filename,
    append=False,
    export_dir=None,
    source_lines=None,
    starting_line=None,
):
    """Export line-by-line profiling data and return the written path.

    Parameters:
        profiling_data (dict): Output of :func:`line_by_line_profile`.
        func (Callable): The profiled function.
        export_format (str): One of ``txt``, ``json``, ``csv``, ``html``,
            ``xml``, ``md``, ``yaml`` or ``toml`` (case-insensitive).
        filename (str): Output filename, with or without the extension.
        append (bool): Append a new run to an existing report instead of
            replacing it (``txt``, ``json``, ``csv``, ``md`` and ``html``).
        export_dir (Optional[str]): Directory for relative ``filename`` values.
        source_lines (Optional[list]): Pre-fetched source lines, used when the
            function has no retrievable source (for example ``exec``-defined).
        starting_line (Optional[int]): First source line number.
    """
    fmt = normalise_format(export_format, allow_none=False)
    _reject_append(fmt, append)
    path = resolve_path(filename, fmt, export_dir=export_dir)
    generated_at = timestamp()[2]

    if source_lines is None or starting_line is None:
        try:
            import inspect

            fetched, start = inspect.getsourcelines(func)
        except (OSError, TypeError):
            fetched, start = [], 0
        source_lines = fetched if source_lines is None else source_lines
        starting_line = start if starting_line is None else starting_line

    rows = _line_rows(profiling_data, func, source_lines, starting_line)
    headers = _headers_for(rows) or [
        "Function Name",
        "Line Number",
        "Source Code",
        "Execution Time (s)",
        "Percent",
        "Memory Usage (MB)",
        "Timestamp",
    ]
    name = profiling_data.get("function_name") or getattr(func, "__name__", "unknown")
    title = f"Line-by-Line Profiling Report: {name}"

    if fmt in ("txt", "csv", "md", "html"):
        return _write_tabular(headers, rows, fmt, path, title, append, generated_at)

    if fmt == "json":
        payload = _json_with_runs("line_by_line_profile", rows, path, append)
        payload["metadata"].update(
            {
                "function_name": name,
                "filepath": profiling_data.get("filepath"),
                "docstring": profiling_data.get("docstring"),
                "total_execution_time": sum(
                    (profiling_data.get("line_execution_times") or {}).values()
                ),
                "peak_memory_usage": profiling_data.get("peak_memory_usage"),
            }
        )
        write_text(path, json.dumps(payload, indent=4, default=str) + "\n")
        return path

    if fmt == "xml":
        root = ET.Element("LineByLineProfile")
        for row in rows:
            line_element = ET.SubElement(root, "Line")
            for key, value in row.items():
                ET.SubElement(line_element, _xml_tag(key)).text = display_value(value)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        return path

    if fmt == "yaml":
        lines = []
        for row in rows:
            lines.append("-")
            for key, value in row.items():
                if isinstance(value, str) and "\n" in value:
                    lines.append(f"  {yaml_key(key)}: |-")
                    for line in value.splitlines():
                        lines.append(f"    {line}")
                else:
                    lines.append(f"  {yaml_key(key)}: {yaml_scalar(value)}")
        write_text(path, "\n".join(lines) + "\n")
        return path

    if fmt == "toml":
        lines = []
        for row in rows:
            lines.append("[[profile]]")
            for key, value in row.items():
                lines.append(f"{toml_key(key)} = {toml_scalar(value)}")
        write_text(path, "\n".join(lines) + "\n")
        return path

    raise ValueError(  # pragma: no cover - normalise_format rejects these
        f"Unsupported export format {export_format!r}; use {_FORMAT_DESCRIPTION}."
    )


# ---------------------------------------------------------------------------
# Generic table export (used for summary reports)
# ---------------------------------------------------------------------------
def export_table(
    rows,
    export_format,
    filename,
    title="FuncProfiler Summary",
    append=False,
    export_dir=None,
    headers=None,
):
    """Export a list of dictionaries as a table and return the written path.

    ``headers`` is only needed when ``rows`` is empty and the report should
    still have a header row.
    """
    fmt = normalise_format(export_format, allow_none=False)
    _reject_append(fmt, append)
    path = resolve_path(filename, fmt, export_dir=export_dir)
    rows = list(rows)
    headers = _headers_for(rows) or list(headers or [])
    generated_at = timestamp()[2]

    if fmt in ("txt", "csv", "md", "html"):
        return _write_tabular(headers, rows, fmt, path, title, append, generated_at)

    if fmt == "json":
        payload = {
            "metadata": {"report": title, "export_time": generated_at},
            "rows": rows,
        }
        if append and os.path.exists(path):
            try:
                existing = json.loads(read_text(path))
            except (OSError, ValueError):
                existing = None
            if isinstance(existing, dict) and isinstance(existing.get("rows"), list):
                payload["rows"] = existing["rows"] + rows
                payload["metadata"]["export_time"] = generated_at
        write_text(path, json.dumps(payload, indent=4, default=str) + "\n")
        return path

    if fmt == "xml":
        root = ET.Element("Table")
        for row in rows:
            row_element = ET.SubElement(root, "Row")
            for key, value in row.items():
                ET.SubElement(row_element, _xml_tag(key)).text = display_value(value)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        return path

    if fmt == "yaml":
        lines = []
        for row in rows:
            lines.append("-")
            for key, value in row.items():
                if isinstance(value, str) and "\n" in value:
                    lines.append(f"  {yaml_key(key)}: |-")
                    for line in value.splitlines():
                        lines.append(f"    {line}")
                else:
                    lines.append(f"  {yaml_key(key)}: {yaml_scalar(value)}")
        write_text(path, "\n".join(lines) + "\n")
        return path

    if fmt == "toml":
        lines = []
        for row in rows:
            lines.append("[[row]]")
            for key, value in row.items():
                lines.append(f"{toml_key(key)} = {toml_scalar(value)}")
        write_text(path, "\n".join(lines) + "\n")
        return path

    raise ValueError(  # pragma: no cover - normalise_format rejects these
        f"Unsupported export format {export_format!r}; use {_FORMAT_DESCRIPTION}."
    )


__all__ = [
    "export_function_profile_data",
    "export_profiling_data",
    "export_table",
]
