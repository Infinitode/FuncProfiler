import unittest
import time
import os
import json
from funcprofiler import (
    function_profile,
    line_by_line_profile,
)

# Sample complex functions to be profiled
@line_by_line_profile(export_format="md", shared_log=False)
def complex_calculations(n):
    """A complex calculation involving nested loops."""
    total = 0
    for i in range(n):
        for j in range(i):
            total += (i * j) ** 0.5
    return total

@line_by_line_profile(shared_log=True)
def conditional_logic(n):
    """A function that uses conditional statements to manipulate a list."""
    result = []
    for i in range(n):
        if i % 3 == 0:
            result.append(i * 2)
        elif i % 5 == 0:
            result.append(i * 3)
        else:
            result.append(i)
    return result

@function_profile(export_format="json", filename="test_json_export")
def json_export_func(n):
    return sum(range(n))

@function_profile(export_format="yaml", filename="test_yaml_export")
def yaml_export_func(n):
    return sum(range(n))

@function_profile(export_format="toml", filename="test_toml_export")
def toml_export_func(n):
    return sum(range(n))

@function_profile(enabled=False, export_format="txt", filename="test_disabled")
def disabled_func(n):
    return sum(range(n))

@line_by_line_profile(shared_log=True)
def function_calls(n):
    """A function that calls a helper function to compute squares."""
    def helper(x):
        return x * x

    total = 0
    for i in range(n):
        total += helper(i)
    return total

@line_by_line_profile(export_format="md", filename="test01")
def simulated_io_operations(n):
    """Simulates I/O operations by sleeping and calculating a sum."""
    total = 0
    for i in range(n):
        if i % 2 == 0:
            time.sleep(0.01)
            total += i
    return total

@function_profile(export_format="html", shared_log=True)
def factorial(n):
    """Computes the factorial of a number."""
    if n == 0:
        return 1
    return n * factorial(n - 1)

class TestFuncProfiler(unittest.TestCase):

    def tearDown(self):
        files_to_remove = [
            "test_json_export.json",
            "test_yaml_export.yaml",
            "test_toml_export.toml",
            "test_disabled.txt",
            "complex_calculations_lblprofile_report.md",
            "test01.md",
            "factorial_funcprofile_report.html",
        ]
        for f in files_to_remove:
            if os.path.exists(f):
                os.remove(f)

    def test_complex_calculations(self):
        result = complex_calculations(10)
        self.assertAlmostEqual(result, 163.8608281556458, places=5)
        self.assertTrue(os.path.exists("complex_calculations_lblprofile_report.md"))

    def test_conditional_logic(self):
        result = conditional_logic(10)
        expected = [0, 1, 2, 6, 4, 15, 12, 7, 8, 18]
        self.assertEqual(result, expected)

    def test_function_calls(self):
        result = function_calls(10)
        self.assertEqual(result, sum(i * i for i in range(10)))

    def test_simulated_io_operations(self):
        result = simulated_io_operations(10)
        expected = sum(i for i in range(10) if i % 2 == 0)
        self.assertEqual(result, expected)

    def test_factorial(self):
        result = factorial(5)
        self.assertEqual(result, 120)

    def test_json_export(self):
        json_export_func(100)
        self.assertTrue(os.path.exists("test_json_export.json"))
        with open("test_json_export.json", 'r') as f:
            data = json.load(f)
            self.assertIn("metadata", data)
            self.assertIn("profile", data)
            self.assertIn("peak_memory_usage", data["profile"])

    def test_yaml_export(self):
        yaml_export_func(100)
        self.assertTrue(os.path.exists("test_yaml_export.yaml"))
        with open("test_yaml_export.yaml", 'r') as f:
            content = f.read()
            self.assertIn("function_name: \"yaml_export_func\"", content)
            self.assertIn("return_value: \"4950\"", content)

    def test_toml_export(self):
        toml_export_func(100)
        self.assertTrue(os.path.exists("test_toml_export.toml"))
        with open("test_toml_export.toml", 'r') as f:
            content = f.read()
            self.assertIn("function_name = \"toml_export_func\"", content)
            self.assertIn("return_value = \"4950\"", content)

    def test_profiling_disabled(self):
        disabled_func(100)
        self.assertFalse(os.path.exists("test_disabled.txt"))

if __name__ == '__main__':
    unittest.main()