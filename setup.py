#!/usr/bin/env python3
"""
Setup script for iTerm2 MCP Server 🐒

Because even monkeys need proper packaging!
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="iterm2-mcp-server",
    version="1.0.0",
    author="Your Favorite Coding Monkey",
    author_email="monkey@example.com",
    description="A Model Context Protocol server for iTerm2 integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/iterm2-mcp-server",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Shells",
        "Topic :: Terminals",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "iterm2-mcp-server=iterm2_mcp_server:main",
        ],
    },
    keywords="iterm2, mcp, model-context-protocol, terminal, automation",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/iterm2-mcp-server/issues",
        "Source": "https://github.com/yourusername/iterm2-mcp-server",
        "Documentation": "https://github.com/yourusername/iterm2-mcp-server#readme",
    },
) 