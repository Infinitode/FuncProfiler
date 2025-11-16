# FuncProfiler
![Python Version](https://img.shields.io/badge/python-3.13-blue.svg)
[![Code Size](https://img.shields.io/github/languages/code-size/infinitode/funcprofiler)](https://github.com/infinitode/funcprofiler)
![Downloads](https://pepy.tech/badge/funcprofiler)
![License Compliance](https://img.shields.io/badge/license-compliance-brightgreen.svg)
![PyPI Version](https://img.shields.io/pypi/v/funcprofiler)

An open-source Python library for identifying bottlenecks in code. It includes function profiling, data exports, logging, and line-by-line profiling for more granular control.

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

FuncProfiler supports Python 3.6 and later.

## Features

- **Function Profiling**: Monitor a function's memory usage and execution time.
- **Line-by-Line Profiling**: Get execution time and memory usage for each line of a function.
- **Shared Logging**: Log profiler outputs to a `.txt` file.
- **File Exports**: Export profiling data in various formats.
- **New Options**:
    - `enabled`: A boolean to enable or disable profiling.
    - `log_level`: Set the logging level to "info" or "debug".

## Export Formats

| Format | `function_profile` | `line_by_line_profile` |
|--------|--------------------|------------------------|
| `txt`  |         ✅         |           ❌           |
| `json` |         ✅         |           ✅           |
| `csv`  |         ✅         |           ✅           |
| `html` |         ✅         |           ✅           |
| `xml`  |         ✅         |           ✅           |
| `md`   |         ✅         |           ✅           |
| `yaml` |         ✅         |           ✅           |
| `toml` |         ✅         |           ✅           |

## Usage

### Function Profiling

```python
from funcprofiler import function_profile

@function_profile(export_format="html", shared_log=True, log_level="debug")
def some_function():
    return "Hello World."

message = some_function()
```

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

## Contributing

Contributions are welcome! Please open an issue or submit a pull request on [GitHub](https://github.com/infinitode/funcprofiler).

## License

FuncProfiler is released under the **MIT License (Modified)**. See the [LICENSE](https://github.com/infinitode/funcprofiler/blob/main/LICENSE) file for details.