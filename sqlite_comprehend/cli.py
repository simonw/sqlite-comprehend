import click
import sqlite_utils
from sqlite_utils.utils import chunks
from .utils import common_boto3_options, make_client


@click.group()
@click.version_option()
def cli():
    "Tools for running data in a SQLite database through AWS Comprehend"


@cli.command
@click.argument(
    "database",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False, exists=True),
)
@click.argument("table")
@click.argument("columns", nargs=-1, required=True)
@click.option("--where", help="WHERE clause to filter table")
@click.option(
    "params",
    "-p",
    "--param",
    multiple=True,
    type=(str, str),
    help="Named :parameters for SQL query",
)
@click.option("-o", "--output", help="Custom output table")
@common_boto3_options
def entities(database, table, columns, where, params, output, **boto_options):
    """
    To extract entities from columns text1 and text2 in mytable:

        sqlite-comprehend entities my.db mytable text1 text2

    To run against just a subset of the rows in the table, add:

        --where "id < :max_id" -p max_id 50

    Results will be written to a table called mytable_comprehend_entities

    To specify a different output table, use -o custom_table_name
    """
    db = sqlite_utils.Database(database)
    comprehend = make_client("comprehend", **boto_options)
    if not db[table].exists():
        raise click.ClickException("Table {} does not exist".format(table))
    if not set(db[table].columns_dict.keys()).issuperset(columns):
        raise click.ClickException(
            "Table {} does not have columns: {}".format(table, ", ".join(columns))
        )
    pks = db[table].pks
    # Create table to write to
    output = output or "{}_comprehend_entities".format(table)
    if not db["comprehend_entity_types"].exists():
        db["comprehend_entity_types"].create(
            {
                "id": int,
                "value": str,
            },
            pk="id",
        )
    if not db[output].exists():
        # Start with columns for the primary keys in the main table
        column_definitions = {pk: db[table].columns_dict[pk] for pk in pks}
        # TODO: what if a primary key clashes with the next columns?
        column_definitions.update(
            {
                "score": float,
                "type": int,
                "text": str,
                "begin_offset": int,
                "end_offset": int,
            }
        )
        foreign_keys = [
            ("type", "comprehend_entity_types", "id"),
        ]
        if len(pks) == 1:
            pk = pks[0]
            foreign_keys.append((pk, table, pk))
        db[output].create(column_definitions, foreign_keys=foreign_keys)

    # Build the SQL query
    sql = "select {} from {}".format(
        ", ".join(list(pks) + list(columns)),
        table,
    )
    if where:
        sql += " where {}".format(where)
    rows = db.query(sql, params=dict(params))

    # Run a count, for the progress bar
    count = next(
        db.query(
            "with t as ({}) select count(*) as c from t".format(sql),
            params=dict(params),
        )
    )["c"]

    with click.progressbar(rows, length=count) as bar:
        # Batch process 25 at a time
        for chunk in chunks(bar, 25):
            chunk = list(chunk)
            # Each input is a max of 5,000 utf-8 bytes
            texts = []
            for row in chunk:
                concat_utf8 = (
                    " ".join((row[column] or "") for column in columns)
                ).encode("utf-8")
                truncated = concat_utf8[:5000]
                # Truncate back to last whitespace to avoid risk of splitting a codepoint
                texts.append(truncated.rsplit(None, 1)[0].decode("utf-8"))

            # Run the batch
            response = comprehend.batch_detect_entities(
                TextList=texts, LanguageCode="en"
            )
            results = response["ResultList"]
            # Match those to their primary keys and insert into output table
            to_insert = []
            for row, result in zip(chunk, results):
                entities = result["Entities"]
                pk_values = {pk: row[pk] for pk in pks}
                to_insert.extend(
                    [
                        dict(
                            **pk_values,
                            score=entity["Score"],
                            type=entity["Type"],
                            text=entity["Text"],
                            begin_offset=entity["BeginOffset"],
                            end_offset=entity["EndOffset"],
                        )
                        for entity in entities
                    ]
                )
            db[output].insert_all(
                to_insert, extracts={"type": "comprehend_entity_types"}
            )
