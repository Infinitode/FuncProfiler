from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

version = "{{VERSION_PLACEHOLDER}}"
if "VERSION_PLACEHOLDER" in version:
    # The release workflow stamps the real version in. Falling back to a valid
    # placeholder keeps `pip install .` working from a plain checkout.
    version = "0.0.0.dev0"

setup(
    name='funcprofiler',
    version=version,
    author='Infinitode Pty Ltd',
    author_email='infinitode.ltd@gmail.com',
    description=(
        'An open-source Python library for finding bottlenecks in code. '
        'Includes function profiling, data exports, logging, and even '
        'line-by-line profiling, for more control.'
    ),
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/infinitode/funcprofiler',
    license='LicenseRef-MIT-Modified',
    project_urls={
        'Source': 'https://github.com/Infinitode/FuncProfiler',
        'Documentation': 'https://github.com/Infinitode/FuncProfiler#readme',
        'Issue Tracker': 'https://github.com/Infinitode/FuncProfiler/issues',
        'Changelog': 'https://github.com/Infinitode/FuncProfiler#changelog-v130',
    },
    packages=find_packages(exclude=('tests', 'tests.*')),
    package_data={'funcprofiler': ['py.typed']},
    include_package_data=True,
    install_requires=[],
    python_requires='>=3.8',
    keywords=[
        'profiler', 'profiling', 'performance', 'bottleneck', 'benchmark',
        'memory', 'line-profiler', 'timing', 'optimization',
    ],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Typing :: Typed',
    ],
)
