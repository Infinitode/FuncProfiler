# FuncProfiler
![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)
[![Code Size](https://img.shields.io/github/languages/code-size/infinitode/funcprofiler)](https://github.com/infinitode/funcprofiler)
![Downloads](https://pepy.tech/badge/funcprofiler)
![License Compliance](https://img.shields.io/badge/license-compliance-brightgreen.svg)
![PyPI Version](https://img.shields.io/pypi/v/funcprofiler)

An open-source Python library for identifying bottlenecks in code. It includes function profiling, data exports, logging, and line-by-line profiling for more granular control.

## Installation

You can install FuncProfiler using pip:

```bash
pip install funcprofiler
```

## Supported Python Versions

FuncProfiler supports the following Python versions:

- Python 3.6
- Python 3.7
- Python 3.8
- Python 3.9
- Python 3.10
- Python 3.11 and later (preferred)

Please ensure that you have one of these Python versions installed. FuncProfiler may not function as expected on earlier versions.

## Features

- **Function Profiling**: Monitor a function's memory usage and execution time to identify performance issues.
- **Line-by-Line Profiling**: Return execution time and memory usage for each line of any given function.
- **Shared Logging**: Log outputs of functions triggered by the line-by-line and function profilers, storing results in a `.txt` file.
- **File Exports**: Export profiling data from functions in `csv`, `json`, or `html` formats.
> [!NOTE]
> View more export types in the [official documentation](https://infinitode-docs.gitbook.io/documentation/package-documentation/funcprofiler-package-documentation).

## Usage

### Function Profiling

```python
from funcprofiler import function_profile

# Exporting as `html` with logging enabled
@function_profile(export_format="html", shared_log=True)
def some_function():
    return "Hello World."

# Call the function
message = some_function()
```

### Line-by-Line Profiling

```python
from funcprofiler import line_by_line_profile

# Logging enabled without exports
@line_by_line_profile(shared_log=True)
def some_complicated_function(n):
    total = 0
    for i in range(n):
        for j in range(i):
            total += (i * j) ** 0.5  # Square root calculation
    return total

# Call the function
total = some_complicated_function(1000)
```

> [!NOTE]
> FuncProfiler can be added to any function using the callable format: `@funcprofiler_function_name(expected_arguments)`.

## Contributing

Contributions are welcome! If you encounter issues, have suggestions, or wish to contribute to FuncProfiler, please open an issue or submit a pull request on [GitHub](https://github.com/infinitode/funcprofiler).

## License

FuncProfiler is released under the terms of the **MIT License (Modified)**. Please see the [LICENSE](https://github.com/infinitode/funcprofiler/blob/main/LICENSE) file for the full text.

**Modified License Clause**: The modified license clause allows users to create derivative works based on the FuncProfiler software. However, it requires that any substantial changes to the software be clearly distinguished from the original work and distributed under a different name.