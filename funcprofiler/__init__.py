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
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not enabled:
                return func(*args, **kwargs)

            # Start time and memory tracking
            tracemalloc.start()
            start_time = time.time()

            # Prepare shared logging if enabled
            log_file = None
            if shared_log:
                log_file = open(log_filename, 'a')
                log_file.write(f"Profiling log for {func.__name__}\n")
                log_file.write(f"Date: {time.strftime('%Y-%m-%d')}\n")
                log_file.write(f"Time: {time.strftime('%H:%M:%S')}\n\n")

            # Execute the function
            result = func(*args, **kwargs)

            # End time and memory tracking
            end_time = time.time()
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            # Prepare data for exporting
            profiling_data = {
                "function_name": func.__name__,
                "execution_times": end_time - start_time,
                "memory_usage": current / 10**6,  # Convert to MB
                "peak_memory_usage": peak / 10**6,
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                "arguments": str({'args': args, 'kwargs': kwargs}),
                "return_value": str(result),
                "filepath": inspect.getfile(func),
                "line_number": inspect.getsourcelines(func)[1],
                "docstring": func.__doc__
            }

            if export_format:
                file = filename or f"{func.__name__}_funcprofile_report"
                export_function_profile_data(profiling_data, func, export_format, file)

            # Display the profiling results
            if log_level == "info":
                print(f"[FUNCPROFILER] Function '{func.__name__}' executed in {end_time - start_time:.12f}s")
                print(f"[FUNCPROFILER] Current memory usage: {current / 10**6:.12f}MB; Peak: {peak / 10**6:.12f}MB")
            elif log_level == "debug":
                print(f"[FUNCPROFILER-DEBUG] Function '{func.__name__}' called with args: {args}, kwargs: {kwargs}")
                print(f"[FUNCPROFILER-DEBUG] Execution Time: {end_time - start_time:.12f}s")
                print(f"[FUNCPROFILER-DEBUG] Memory Usage: {current / 10**6:.6f}MB; Peak: {peak / 10**6:.6f}MB")
                print(f"[FUNCPROFILER-DEBUG] Return Value: {result}")

            # Log the profiling data
            if shared_log and log_file:
                log_file.write(f"Function {func.__name__} called with args: {args}, kwargs: {kwargs}\n")
                log_file.write(f"Execution Time: {end_time - start_time:.12f}s, Memory usage: {current / 10**6:.6f}MB; Peak: {peak / 10**6:.6f}MB\n")
                log_file.write("-" * 40 + "\n")  # Separator between calls

            if shared_log and log_file:
                log_file.close()  # Close the log file after writing if shared_log is True

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
        with open(f"{filename}.html", 'w') as f:
            f.write("<html><head><title>Function Profiling Report</title>")
            f.write("""
            <style>
                body { font-family: Arial, sans-serif; }
                table { border-collapse: collapse; width: 60%; margin: 20px 0; }
                th, td { border: 1px solid #dddddd; text-align: left; padding: 8px; }
                th { background-color: #f2f2f2; }
            </style>
            """)
            f.write("</head><body>")
            f.write(f"<h1>Function Profiling Report: {profiling_data['function_name']}</h1>")
            f.write("<table>")
            f.write("<tr><th>Metric</th><th>Value</th></tr>")
            for key, value in profiling_data.items():
                f.write(f"<tr><td>{key.replace('_', ' ').title()}</td><td>{value}</td></tr>")
            f.write("</table>")
            f.write("</body></html>")

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
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not enabled:
                return func(*args, **kwargs)

            line_execution_times: Dict[int, float] = {}
            line_memory_usage: Dict[int, float] = {}
            current_line_start_time: Optional[float] = None
            timer = time.perf_counter
            tracemalloc.start()

            # Prepare shared logging if enabled
            log_file = None
            if shared_log:
                log_file = open(log_filename, 'a')
                log_file.write(f"Profiling log for {func.__name__}\n")
                log_file.write(f"Date: {time.strftime('%Y-%m-%d')}\n")
                log_file.write(f"Time: {time.strftime('%H:%M:%S')}\n\n")

            def trace_lines(frame, event, arg):
                nonlocal current_line_start_time
                if frame.f_code.co_name == func.__name__:
                    lineno = frame.f_lineno
                    if event == 'line':
                        current_memory = tracemalloc.get_traced_memory()[1] / 10**6  # Convert to MB
                        if current_line_start_time is not None:
                            elapsed_time = timer() - current_line_start_time
                            if lineno in line_execution_times:
                                line_execution_times[lineno] += elapsed_time
                            else:
                                line_execution_times[lineno] = elapsed_time
                            line_memory_usage[lineno] = current_memory

                            # Log the profiling data
                            if shared_log and log_file:
                                log_file.write(f"Line {lineno}: Execution Time: {elapsed_time:.12f}s, Memory Usage: {current_memory:.12f}MB\n")

                        current_line_start_time = timer()
                return trace_lines

            sys.settrace(trace_lines)
            try:
                result = func(*args, **kwargs)
            finally:
                sys.settrace(None)
                tracemalloc.stop()

            # Print profiling data
            if log_level == "info":
                print(f"\nLine-by-Line Profiling for '{func.__name__}':")
                source_lines, starting_line = inspect.getsourcelines(func)
                for line_no in sorted(line_execution_times.keys()):
                    actual_line = line_no - starting_line + 1
                    source_line = source_lines[actual_line - 1].strip()
                    exec_time = line_execution_times[line_no]
                    mem_usage = line_memory_usage.get(line_no, 0)
                    print(f"Line {line_no} ({source_line}): "
                          f"Execution Time: {exec_time:.12f}s, "
                          f"Memory Usage: {mem_usage:.12f}MB")
            elif log_level == "debug":
                print(f"\n[DEBUG] Line-by-Line Profiling for '{func.__name__}':")
                source_lines, starting_line = inspect.getsourcelines(func)
                for line_no in sorted(line_execution_times.keys()):
                    actual_line = line_no - starting_line + 1
                    source_line = source_lines[actual_line - 1].strip()
                    exec_time = line_execution_times[line_no]
                    mem_usage = line_memory_usage.get(line_no, 0)
                    print(f"[DEBUG] Line {line_no} ({source_line}): "
                          f"Execution Time: {exec_time:.12f}s, "
                          f"Memory Usage: {mem_usage:.12f}MB")

            # Collect the profiling data for the report
            profiling_data = {
                "function_name": func.__name__,
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                "arguments": str({'args': args, 'kwargs': kwargs}),
                "return_value": str(result),
                "filepath": inspect.getfile(func),
                "docstring": func.__doc__,
                "line_execution_times": line_execution_times,
                "line_memory_usage": line_memory_usage
            }

            if export_format:
                file = filename or f"{func.__name__}_lblprofile_report"
                export_profiling_data(profiling_data, func, export_format, file)

            # Close the log file if shared logging was enabled
            if shared_log and log_file:
                log_file.write("\n")  # Add a new line for separation
                log_file.write("-" * 40 + "\n")  # Separator between calls
                log_file.write("\n")  # Add a new line for separation
                log_file.close()

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
        file_mode = 'a' if os.path.exists(output_path) else 'w'
        if file_mode == 'w':
            html_content = f"""
            <html>
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
                    </tr>
            """
        else:
            with open(output_path, 'r') as f:
                html_content = f.read().replace("</table></body></html>", "")

        for data in export_data:
            html_content += f"""
            <tr>
                <td>{data['Line Number']}</td>
                <td>{data['Source Code']}</td>
                <td>{data['Execution Time (s)']}</td>
                <td>{data['Memory Usage (MB)']}</td>
            </tr>
            """
        html_content += "</table></body></html>"
        with open(output_path, 'w') as f:
            f.write(html_content)
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