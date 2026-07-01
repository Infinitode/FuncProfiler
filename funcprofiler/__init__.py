import time
import tracemalloc
import functools
import inspect
import os
import sys
import csv
import json
from typing import Callable, List, Dict, Optional
import xml.etree.ElementTree as ET

__all__ = ['function_profile', 'line_by_line_profile', 'export_function_profile_data', 'export_profiling_data']

def function_profile(export_format: Optional[str] = None, filename: Optional[str] = None, shared_log: bool = False, enabled: bool = True, log_level: str = "info") -> Callable:
    """Decorator factory to profile the execution time and memory usage of a function.

    Parameters:
        export_format (Optional[str]): The format to export the profiling data ('txt', 'json', 'csv', 'html').
        filename (Optional[str]): The name of the output file (without extension).
        shared_log (Optional[bool]): If True, log to a shared file for all profiled functions.
        enabled (bool): If False, the decorator will not perform any profiling.
        log_level (str): The logging level ("info" or "debug").
    Returns:
        Callable: The profiling wrapper or decorator function.
    """
    log_filename = f"func_profiler_logs_{time.strftime('%Y%m%d')}_{time.strftime('%H%M%S')}.txt"

    def decorator(func: Callable) -> Callable:
        # Pre-fetch metadata
        func_name = func.__name__
        try:
            filepath = inspect.getfile(func)
        except (TypeError, ValueError):
            filepath = "unknown"
        try:
            line_number = inspect.getsourcelines(func)[1]
        except (IOError, TypeError):
            line_number = 0
        docstring = func.__doc__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not enabled:
                return func(*args, **kwargs)

            # Start time and memory tracking
            tracemalloc.start()
            start_time = time.time()

            # Execute the function
            result = func(*args, **kwargs)

            # End time and memory tracking
            end_time = time.time()
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            # Prepare data for exporting
            execution_time = end_time - start_time
            current_mb = current / 10**6
            peak_mb = peak / 10**6

            if export_format or log_level == "debug" or shared_log:
                now = time.localtime()
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', now)

                # Prepare shared logging if enabled
                if shared_log:
                    with open(log_filename, 'a') as log_file:
                        date_str = timestamp[:10]
                        time_str = timestamp[11:]
                        log_file.write(f"Profiling log for {func_name}\n")
                        log_file.write(f"Date: {date_str}\n")
                        log_file.write(f"Time: {time_str}\n\n")
                        log_file.write(f"Function {func_name} called with args: {args}, kwargs: {kwargs}\n")
                        log_file.write(f"Execution Time: {execution_time:.12f}s, Memory usage: {current_mb:.6f}MB; Peak: {peak_mb:.6f}MB\n")
                        log_file.write("-" * 40 + "\n")

                if export_format:
                    profiling_data = {
                        "function_name": func_name,
                        "execution_times": execution_time,
                        "memory_usage": current_mb,
                        "peak_memory_usage": peak_mb,
                        "timestamp": timestamp,
                        "arguments": str({'args': args, 'kwargs': kwargs}),
                        "return_value": str(result),
                        "filepath": filepath,
                        "line_number": line_number,
                        "docstring": docstring
                    }
                    file = filename or f"{func_name}_funcprofile_report"
                    export_function_profile_data(profiling_data, func, export_format, file)

            # Display the profiling results
            if log_level == "info":
                print(f"[FUNCPROFILER] Function '{func_name}' executed in {execution_time:.12f}s")
                print(f"[FUNCPROFILER] Current memory usage: {current_mb:.12f}MB; Peak: {peak_mb:.12f}MB")
            elif log_level == "debug":
                print(f"[FUNCPROFILER-DEBUG] Function '{func_name}' called with args: {args}, kwargs: {kwargs}")
                print(f"[FUNCPROFILER-DEBUG] Execution Time: {execution_time:.12f}s")
                print(f"[FUNCPROFILER-DEBUG] Memory Usage: {current_mb:.6f}MB; Peak: {peak_mb:.6f}MB")
                print(f"[FUNCPROFILER-DEBUG] Return Value: {result}")

            return result

        return wrapper

    return decorator

def export_function_profile_data(profiling_data: dict, func: Callable, export_format: str, filename: str) -> None:
    """Export profiling data for the function profile to the specified format.

    Parameters:
        profiling_data (dict): The profiling data containing execution time and memory usage.
        func (Callable): The function that was profiled.
        export_format (str): The format for export ('txt', 'json', 'csv', 'html', 'xml', 'md').
        filename (str): The output filename without extension.
    """
    if export_format == "txt":
        with open(f"{filename}.txt", 'w') as f:
            for key, value in profiling_data.items():
                f.write(f"{key.replace('_', ' ').title()}: {value}\n")

    elif export_format == "json":
        output_data = {
            "metadata": {
                "profile_type": "function_profile",
                "export_time": time.strftime('%Y-%m-%d %H:%M:%S')
            },
            "profile": profiling_data
        }
        with open(f"{filename}.json", 'w') as f:
            json.dump(output_data, f, indent=4)

    elif export_format == "csv":
        with open(f"{filename}.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(profiling_data.keys())
            writer.writerow(profiling_data.values())

    elif export_format == "html":
        html_lines = [
            "<html><head><title>Function Profiling Report</title>",
            "<style>",
            "    body { font-family: Arial, sans-serif; }",
            "    table { border-collapse: collapse; width: 60%; margin: 20px 0; }",
            "    th, td { border: 1px solid #dddddd; text-align: left; padding: 8px; }",
            "    th { background-color: #f2f2f2; }",
            "</style>",
            "</head><body>",
            f"<h1>Function Profiling Report: {profiling_data['function_name']}</h1>",
            "<table>",
            "<tr><th>Metric</th><th>Value</th></tr>"
        ]
        for key, value in profiling_data.items():
            html_lines.append(f"<tr><td>{key.replace('_', ' ').title()}</td><td>{value}</td></tr>")
        html_lines.append("</table></body></html>")
        with open(f"{filename}.html", 'w') as f:
            f.write("\n".join(html_lines))

    elif export_format == "xml":
        root = ET.Element("FunctionProfile")
        for key, value in profiling_data.items():
            ET.SubElement(root, key.replace('_', ' ').title().replace(' ', '')).text = str(value)
        tree = ET.ElementTree(root)
        tree.write(f"{filename}.xml")

    elif export_format == "md":
        with open(f"{filename}.md", 'w') as f:
            f.write(f"# Function Profiling Report for {profiling_data['function_name']}\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            for key, value in profiling_data.items():
                f.write(f"| {key.replace('_', ' ').title()} | {value} |\n")

    elif export_format == "yaml":
        def to_yaml_string(data):
            lines = []
            for key, value in data.items():
                if isinstance(value, str) and '\n' in value:
                    lines.append(f"{key}: |")
                    for line in value.splitlines():
                        lines.append(f"  {line}")
                else:
                    lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
            return "\n".join(lines)

        with open(f"{filename}.yaml", 'w') as f:
            f.write(to_yaml_string(profiling_data))

    elif export_format == "toml":
        def to_toml_string(data):
            lines = []
            for key, value in data.items():
                if isinstance(value, str) and '\n' in value:
                    lines.append(f"{key} = '''\n{value}'''")
                else:
                    lines.append(f"{key} = {json.dumps(value, ensure_ascii=False)}")
            return "\n".join(lines)

        with open(f"{filename}.toml", 'w') as f:
            f.write(to_toml_string(profiling_data))

    else:
        raise ValueError("Unsupported export format. Use 'txt', 'json', 'csv', 'html', 'xml', 'md', 'yaml', or 'toml'.")

def line_by_line_profile(
    export_format: Optional[str] = None,
    filename: Optional[str] = None,
    shared_log: bool = False,
    enabled: bool = True,
    log_level: str = "info"
) -> Callable:
    """Decorator for line-by-line profiling of a function with optional data export and shared logging.

    Parameters:
        export_format (Optional[str]): The format to export the profiling data ('json', 'csv', 'html').
        filename (Optional[str]): The name of the output file (without extension).
        shared_log (Optional[bool]): If True, log to a shared file for all profiled functions.
        enabled (bool): If False, the decorator will not perform any profiling.
        log_level (str): The logging level ("info" or "debug").
    Returns:
        Callable: The profiling wrapper or decorator function.
    """
    log_filename = f"lbl_profiler_logs_{time.strftime('%Y%m%d')}_{time.strftime('%H%M%S')}.txt"

    def decorator(func: Callable) -> Callable:
        # Pre-fetch metadata
        func_name = func.__name__
        target_code = func.__code__
        try:
            filepath = inspect.getfile(func)
        except (TypeError, ValueError):
            filepath = "unknown"
        try:
            source_lines, starting_line = inspect.getsourcelines(func)
        except (IOError, TypeError):
            source_lines, starting_line = [], 0
        docstring = func.__doc__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not enabled:
                return func(*args, **kwargs)

            line_execution_times: Dict[int, float] = {}
            line_memory_usage: Dict[int, float] = {}
            current_line_start_time: Optional[float] = None
            last_lineno: Optional[int] = None
            timer = time.perf_counter
            tracemalloc.start()

            # Prepare shared logging buffer if enabled
            log_buffer = []
            if shared_log:
                now = time.localtime()
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', now)
                log_buffer.append(f"Profiling log for {func_name}\n")
                log_buffer.append(f"Date: {timestamp[:10]}\n")
                log_buffer.append(f"Time: {timestamp[11:]}\n\n")

            def trace_lines(frame, event, arg):
                nonlocal current_line_start_time, last_lineno
                if frame.f_code is target_code:
                    if event == 'line':
                        now = timer()
                        lineno = frame.f_lineno
                        if current_line_start_time is not None and last_lineno is not None:
                            elapsed_time = now - current_line_start_time
                            line_execution_times[last_lineno] = line_execution_times.get(last_lineno, 0.0) + elapsed_time

                            current_memory = tracemalloc.get_traced_memory()[1] / 10**6  # Convert to MB
                            line_memory_usage[last_lineno] = current_memory

                            # Buffer the profiling data
                            if shared_log:
                                log_buffer.append(f"Line {last_lineno}: Execution Time: {elapsed_time:.12f}s, Memory Usage: {current_memory:.12f}MB\n")

                        current_line_start_time = now
                        last_lineno = lineno
                    elif event == 'return':
                        if current_line_start_time is not None and last_lineno is not None:
                            elapsed_time = timer() - current_line_start_time
                            line_execution_times[last_lineno] = line_execution_times.get(last_lineno, 0.0) + elapsed_time
                            current_memory = tracemalloc.get_traced_memory()[1] / 10**6
                            line_memory_usage[last_lineno] = current_memory
                            if shared_log:
                                log_buffer.append(f"Line {last_lineno}: Execution Time: {elapsed_time:.12f}s, Memory Usage: {current_memory:.12f}MB\n")
                return trace_lines

            sys.settrace(trace_lines)
            try:
                result = func(*args, **kwargs)
            finally:
                sys.settrace(None)
                tracemalloc.stop()

            # Print profiling data
            if log_level in ("info", "debug"):
                prefix = "[DEBUG] " if log_level == "debug" else ""
                print(f"\n{prefix}Line-by-Line Profiling for '{func_name}':")
                for line_no in sorted(line_execution_times.keys()):
                    actual_line = line_no - starting_line + 1
                    source_line = source_lines[actual_line - 1].strip() if 0 < actual_line <= len(source_lines) else "???"
                    exec_time = line_execution_times[line_no]
                    mem_usage = line_memory_usage.get(line_no, 0)
                    print(f"{prefix}Line {line_no} ({source_line}): "
                          f"Execution Time: {exec_time:.12f}s, "
                          f"Memory Usage: {mem_usage:.12f}MB")

            # Handle shared logging
            if shared_log:
                log_buffer.append("\n" + "-" * 40 + "\n\n")
                with open(log_filename, 'a') as log_file:
                    log_file.write("".join(log_buffer))

            # Collect the profiling data for the report
            if export_format:
                profiling_data = {
                    "function_name": func_name,
                    "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "arguments": str({'args': args, 'kwargs': kwargs}),
                    "return_value": str(result),
                    "filepath": filepath,
                    "docstring": docstring,
                    "line_execution_times": line_execution_times,
                    "line_memory_usage": line_memory_usage
                }
                file = filename or f"{func_name}_lblprofile_report"
                export_profiling_data(profiling_data, func, export_format, file)

            return result

        return wrapper

    # If no arguments are provided, it means func is passed directly
    if callable(export_format):
        actual_func = export_format
        export_format = None
        return decorator(actual_func)

    return decorator

def export_profiling_data(
    profiling_data: Dict[str, Dict[int, float]],
    func: Callable,
    export_format: str,
    filename: str
) -> None:
    """Export the profiling data to the specified format (JSON, CSV, HTML, XML, MD).

    Parameters:
        profiling_data (Dict[str, Dict[int, float]]): Profiling data to be exported.
        func (Callable): The function that was profiled.
        export_format (str): The format for export ('json', 'csv', 'html', 'xml', 'md').
        filename (str): The output filename without extension.
    """
    line_execution_times = profiling_data["line_execution_times"]
    line_memory_usage = profiling_data["line_memory_usage"]

    # Get the source code of the function
    source_lines, starting_line = inspect.getsourcelines(func)

    # Prepare data for export
    export_data: List[Dict[str, str]] = []
    for line_no in sorted(line_execution_times.keys()):
        actual_line = line_no - starting_line + 1
        source_line = source_lines[actual_line - 1].strip()
        exec_time = line_execution_times[line_no]
        mem_usage = line_memory_usage.get(line_no, 0)

        # Conditional wrapping based on the export format
        wrapped_source_code = f'"{source_line}"' if export_format == 'csv' else source_line

        export_data.append({
            'Function Name': func.__name__,
            'Line Number': str(line_no),
            'Source Code': wrapped_source_code,  # Use wrapped source code
            'Execution Time (s)': f"{exec_time:.12f}",
            'Memory Usage (MB)': f"{mem_usage:.12f}"
        })

    # Handle different export formats
    if export_format == 'json':
        output_data = {
            "metadata": {
                "profile_type": "line_by_line_profile",
                "export_time": time.strftime('%Y-%m-%d %H:%M:%S'),
                "function_name": func.__name__,
                "filepath": inspect.getfile(func),
                "docstring": func.__doc__
            },
            "profile": export_data
        }
        with open(f"{filename}.json", 'w') as json_file:
            json.dump(output_data, json_file, indent=4)
        print(f"[PROFILER] JSON report generated at: {filename}.json")

    elif export_format == 'csv':
        output_path = f"{filename}.csv"
        file_mode = 'a' if os.path.exists(output_path) else 'w'
        with open(output_path, mode=file_mode, newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=export_data[0].keys())
            if file_mode == 'w':
                writer.writeheader()
            writer.writerows(export_data)
        print(f"[PROFILER] CSV report generated at: {output_path}")

    elif export_format == 'html':
        output_path = f"{filename}.html"
        html_lines = []
        if os.path.exists(output_path):
            with open(output_path, 'r') as f:
                html_content = f.read()
            # If it's a valid HTML report, insert before </table>
            if "</table></body></html>" in html_content:
                html_parts = html_content.split("</table></body></html>")
                html_lines.append(html_parts[0])
            else:
                html_lines.append(html_content)
        else:
            html_lines.append(f"""<html>
<head>
    <title>Line-by-Line Profiling Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #dddddd; text-align: left; padding: 8px; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h2>Line-by-Line Profiling Report for {func.__name__}</h2>
    <table>
        <tr>
            <th>Line Number</th>
            <th>Source Code</th>
            <th>Execution Time (s)</th>
            <th>Memory Usage (MB)</th>
        </tr>""")

        for data in export_data:
            html_lines.append(f"""        <tr>
            <td>{data['Line Number']}</td>
            <td>{data['Source Code']}</td>
            <td>{data['Execution Time (s)']}</td>
            <td>{data['Memory Usage (MB)']}</td>
        </tr>""")

        html_lines.append("    </table>\n</body>\n</html>")
        with open(output_path, 'w') as f:
            f.write("\n".join(html_lines))
        print(f"[PROFILER] HTML report generated at: {output_path}")

    elif export_format == 'xml':
        root = ET.Element("LineByLineProfile")
        for data in export_data:
            line_element = ET.SubElement(root, "Line")
            for key, value in data.items():
                ET.SubElement(line_element, key.replace(' ', '')).text = str(value)
        tree = ET.ElementTree(root)
        tree.write(f"{filename}.xml")
        print(f"[PROFILER] XML report generated at: {filename}.xml")

    elif export_format == 'md':
        with open(f"{filename}.md", 'w') as f:
            f.write(f"# Line-by-Line Profiling Report for {func.__name__}\n\n")
            f.write("| Line Number | Source Code | Execution Time (s) | Memory Usage (MB) |\n")
            f.write("|-------------|-------------|--------------------|-------------------|\n")
            for data in export_data:
                f.write(f"| {data['Line Number']} | `{data['Source Code']}` | {data['Execution Time (s)']} | {data['Memory Usage (MB)']} |\n")
        print(f"[PROFILER] Markdown report generated at: {filename}.md")

    elif export_format == 'yaml':
        def to_yaml_string(data):
            lines = []
            for item in data:
                lines.append("-")
                for key, value in item.items():
                    if isinstance(value, str) and '\n' in value:
                        lines.append(f"  {key}: |")
                        for line in value.splitlines():
                            lines.append(f"    {line}")
                    else:
                        lines.append(f"  {key}: {json.dumps(value, ensure_ascii=False)}")
            return "\n".join(lines)

        with open(f"{filename}.yaml", 'w') as f:
            f.write(to_yaml_string(export_data))

    elif export_format == 'toml':
        def to_toml_string(data):
            lines = []
            for item in data:
                lines.append("[[profile]]")
                for key, value in item.items():
                    if isinstance(value, str) and '\n' in value:
                        lines.append(f"{key} = '''\n{value}'''")
                    else:
                        lines.append(f"{key} = {json.dumps(value, ensure_ascii=False)}")
            return "\n".join(lines)

        with open(f"{filename}.toml", 'w') as f:
            f.write(to_toml_string(export_data))

    else:
        print(f"[PROFILER] Unsupported export format: {export_format}")