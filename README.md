# sqlite-comprehend

[![PyPI](https://img.shields.io/pypi/v/sqlite-comprehend.svg)](https://pypi.org/project/sqlite-comprehend/)
[![Changelog](https://img.shields.io/github/v/release/simonw/sqlite-comprehend?include_prereleases&label=changelog)](https://github.com/simonw/sqlite-comprehend/releases)
[![Tests](https://github.com/simonw/sqlite-comprehend/workflows/Test/badge.svg)](https://github.com/simonw/sqlite-comprehend/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/simonw/sqlite-comprehend/blob/master/LICENSE)

Tools for running data in a SQLite database through [AWS Comprehend]()

## Installation

Install this tool using `pip`:

    pip install sqlite-comprehend

## Entity extraction

The `sqlite-comprehend entities` command runs entity extraction against every row in the specified table and saves the results to your database.

Specify the database, the table and one or more columns containing text in that table. The following runs against the `text` column in the `pages` table of the `sfms.db` SQLite database:

    sqlite-comprehend sfms.db pages text

Results will be written into a `pages_comprehend_entities` table. Change the name of the output table by passing `-o other_table_name`.

You can run against a subset of rows by adding a `--where` clause:

    sqlite-comprehend sfms.db pages text --where 'id < 10'

You can also used named parameters in your `--where` clause:

    sqlite-comprehend sfms.db pages text --where 'id < :maxid' -p maxid 10

## Schema

The tables creatyd by this tool have the following schema:

```sql
CREATE TABLE [comprehend_entity_types] (
   [id] INTEGER PRIMARY KEY,
   [value] TEXT
);

CREATE UNIQUE INDEX [idx_comprehend_entity_types_value]
    ON [comprehend_entity_types] ([value]);

CREATE TABLE [pages_comprehend_entities] (
   [id] TEXT REFERENCES [pages]([id]),
   [score] FLOAT,
   [type] INTEGER REFERENCES [comprehend_entity_types]([id]),
   [text] TEXT,
   [begin_offset] INTEGER,
   [end_offset] INTEGER
);
```
## Development

To contribute to this tool, first checkout the code. Then create a new virtual environment:

    cd sqlite-comprehend
    python -m venv venv
    source venv/bin/activate

Now install the dependencies and test dependencies:

    pip install -e '.[test]'

To run the tests:

    pytest
