import unittest
import time
from funcprofiler import (
    function_profile,
    line_by_line_profile,
)

# Sample complex functions to be profiled
@line_by_line_profile(export_format="json", shared_log=False)
def complex_calculations(n):
    """A complex calculation involving nested loops."""
    total = 0
    for i in range(n):
        for j in range(i):
            total += (i * j) ** 0.5  # Square root calculation
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

@line_by_line_profile(shared_log=True)
def function_calls(n):
    """A function that calls a helper function to compute squares."""
    def helper(x):
        return x * x  # Example helper function

    total = 0
    for i in range(n):
        total += helper(i)
    return total

@line_by_line_profile(export_format="csv", filename="test01")
def simulated_io_operations(n):
    """Simulates I/O operations by sleeping and calculating a sum."""
    total = 0
    for i in range(n):
        if i % 2 == 0:
            time.sleep(0.01)  # Simulate a blocking I/O operation
            total += i
    return total

@function_profile(export_format="html", shared_log=True)
def factorial(n):
    """Computes the factorial of a number."""
    if n == 0:
        return 1
    return n * factorial(n - 1)

class TestFuncProfiler(unittest.TestCase):

    def test_complex_calculations(self):
        result = complex_calculations(10)
        self.assertAlmostEqual(result, 163.8608281556458, places=5)

    def test_conditional_logic(self):
        result = conditional_logic(10)
        expected = [0, 1, 2, 6, 4, 15, 12, 7, 8, 18]
        self.assertEqual(result, expected)

    def test_function_calls(self):
        result = function_calls(10)
        self.assertEqual(result, sum(i * i for i in range(10)))

    def test_simulated_io_operations(self):
        result = simulated_io_operations(10)
        expected = sum(i for i in range(10) if i % 2 == 0)  # Sum of even numbers from 0 to 9
        self.assertEqual(result, expected)

    def test_factorial(self):
        result = factorial(5)
        self.assertEqual(result, 120)  # 5! = 120

if __name__ == '__main__':
    unittest.main()