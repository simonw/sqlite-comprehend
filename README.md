# sqlite-comprehend

[![PyPI](https://img.shields.io/pypi/v/sqlite-comprehend.svg)](https://pypi.org/project/sqlite-comprehend/)
[![Changelog](https://img.shields.io/github/v/release/simonw/sqlite-comprehend?include_prereleases&label=changelog)](https://github.com/simonw/sqlite-comprehend/releases)
[![Tests](https://github.com/simonw/sqlite-comprehend/workflows/Test/badge.svg)](https://github.com/simonw/sqlite-comprehend/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/simonw/sqlite-comprehend/blob/master/LICENSE)

Tools for running data in a SQLite database through [AWS Comprehend]()

## Installation

Install this tool using `pip`:

    pip install sqlite-comprehend

## Configuration

You will need AWS credentials with the `comprehend:DetectEntities` [IAM permission](https://docs.aws.amazon.com/comprehend/latest/dg/access-control-managing-permissions.html).

You can configure credentials [using these instructions](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html). You can also save them to a JSON or INI configuration file and pass them to the command using `-a credentials.ini`, or pass them using the `--access-key` and `--secret-key` options.

## Entity extraction

The `sqlite-comprehend entities` command runs entity extraction against every row in the specified table and saves the results to your database.

Specify the database, the table and one or more columns containing text in that table. The following runs against the `text` column in the `pages` table of the `sfms.db` SQLite database:

    sqlite-comprehend sfms.db pages text

Results will be written into a `pages_comprehend_entities` table. Change the name of the output table by passing `-o other_table_name`.

You can run against a subset of rows by adding a `--where` clause:

    sqlite-comprehend sfms.db pages text --where 'id < 10'

You can also used named parameters in your `--where` clause:

    sqlite-comprehend sfms.db pages text --where 'id < :maxid' -p maxid 10

Only the first 5,000 characters for each row will be considered. Be sure to review [Comprehend's pricing](https://aws.amazon.com/comprehend/pricing/) - which starts at $0.0001 per hundred characters.

## Schema

Assuming an input table called `pages` the tables created by this tool will have the following schema:

<!-- [[[cog
import cog, json
from sqlite_comprehend import cli
from unittest.mock import patch
from click.testing import CliRunner
import sqlite_utils
import tempfile, pathlib
tmpdir = pathlib.Path(tempfile.mkdtemp())
db_path = str(tmpdir / "data.db")
db = sqlite_utils.Database(db_path)
db["pages"].insert_all(
    [
        {
            "id": 1,
            "text": "John Bob",
        },
        {
            "id": 2,
            "text": "Sandra X",
        },
    ],
    pk="id",
)
with patch('boto3.client') as client:
    client.return_value.batch_detect_entities.return_value = {
        "ResultList": [
            {
                "Index": 0,
                "Entities": [
                    {
                        "Score": 0.8,
                        "Type": "PERSON",
                        "Text": "John Bob",
                        "BeginOffset": 0,
                        "EndOffset": 5,
                    },
                ],
            },
            {
                "Index": 1,
                "Entities": [
                    {
                        "Score": 0.8,
                        "Type": "PERSON",
                        "Text": "Sandra X",
                        "BeginOffset": 0,
                        "EndOffset": 5,
                    },
                ],
            },
        ],
        "ErrorList": [],
    }
    runner = CliRunner()
    result = runner.invoke(cli.cli, [
        "entities", db_path, "pages", "text"
    ])
cog.out("```sql\n")
cog.out(db.schema)
cog.out("\n```")
]]] -->
```sql
CREATE TABLE [pages] (
   [id] INTEGER PRIMARY KEY,
   [text] TEXT
);
CREATE TABLE [comprehend_entity_types] (
   [id] INTEGER PRIMARY KEY,
   [value] TEXT
);
CREATE TABLE [comprehend_entities] (
   [id] INTEGER PRIMARY KEY,
   [name] TEXT,
   [type] INTEGER REFERENCES [comprehend_entity_types]([id])
);
CREATE TABLE [pages_comprehend_entities] (
   [id] INTEGER REFERENCES [pages]([id]),
   [score] FLOAT,
   [entity] INTEGER REFERENCES [comprehend_entities]([id]),
   [begin_offset] INTEGER,
   [end_offset] INTEGER
);
CREATE UNIQUE INDEX [idx_comprehend_entity_types_value]
    ON [comprehend_entity_types] ([value]);
CREATE UNIQUE INDEX [idx_comprehend_entities_type_name]
    ON [comprehend_entities] ([type], [name]);
```
<!-- [[[end]]] -->

## Development

To contribute to this tool, first checkout the code. Then create a new virtual environment:

    cd sqlite-comprehend
    python -m venv venv
    source venv/bin/activate

Now install the dependencies and test dependencies:

    pip install -e '.[test]'

To run the tests:

    pytest
