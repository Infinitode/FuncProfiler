from setuptools import setup, find_packages

setup(
    name='funcprofiler',
    version='{{VERSION_PLACEHOLDER}}',
    author='Infinitode Pty Ltd',
    author_email='infinitode.ltd@gmail.com',
    description='An open-source Python library that can be used to profile functions.',
    long_description='An open-source Python library for finding bottlenecks in code. Includes function profiling, data exports, logging, and even line-by-line profiling, for more control.',
    long_description_content_type='text/markdown',
    url='https://github.com/infinitode/valx',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
    python_requires='>=3.6',
)
