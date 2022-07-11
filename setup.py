from setuptools import setup
import os

VERSION = "0.2"


def get_long_description():
    with open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md"),
        encoding="utf8",
    ) as fp:
        return fp.read()


setup(
    name="sqlite-comprehend",
    description="Tools for running data in a SQLite database through AWS Comprehend",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="Simon Willison",
    url="https://github.com/simonw/sqlite-comprehend",
    project_urls={
        "Issues": "https://github.com/simonw/sqlite-comprehend/issues",
        "CI": "https://github.com/simonw/sqlite-comprehend/actions",
        "Changelog": "https://github.com/simonw/sqlite-comprehend/releases",
    },
    license="Apache License, Version 2.0",
    version=VERSION,
    packages=["sqlite_comprehend"],
    entry_points="""
        [console_scripts]
        sqlite-comprehend=sqlite_comprehend.cli:cli
    """,
    install_requires=["click", "boto3", "sqlite-utils"],
    extras_require={"test": ["pytest", "pytest-mock", "cogapp"]},
    python_requires=">=3.7",
)
