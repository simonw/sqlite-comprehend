import click
import sqlite_utils
import json
from sqlite_utils.utils import chunks
from .utils import common_boto3_options, make_client, strip_tags


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
@click.option(
    "-r", "--reset", is_flag=True, help="Start from scratch, deleting previous results"
)
@click.option(
    "should_strip_tags",
    "--strip-tags",
    is_flag=True,
    help="Strip HTML tags before extracting entities",
)
@common_boto3_options
def entities(
    database,
    table,
    columns,
    where,
    params,
    output,
    reset,
    should_strip_tags,
    **boto_options
):
    """
    Detect entities in columns in a table

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
    output_table = output or "{}_comprehend_entities".format(table)
    done_table = "{}_done".format(output_table)

    if reset:
        db[output_table].drop(True)
        db[done_table].drop(True)
        db["comprehend_entity_types"].drop(True)
        db["comprehend_entities"].drop(True)

    if not db["comprehend_entity_types"].exists():
        db["comprehend_entity_types"].create(
            {
                "id": int,
                "value": str,
            },
            pk="id",
        )

    entities_table = db.table("comprehend_entities")
    if not entities_table.exists():
        entities_table.create(
            {"id": int, "name": str, "type": int},
            pk="id",
            foreign_keys=[("type", "comprehend_entity_types", "id")],
        )

    if not db[output_table].exists():
        # Start with columns for the primary keys in the main table
        column_definitions = {pk: db[table].columns_dict[pk] for pk in pks}
        reserved_columns = {"score", "entity", "begin_offset", "end_offset"}
        if set(pks).intersection(reserved_columns):
            raise click.ClickException(
                "Primary keys {} overlap with reserved columns: {}".format(
                    ", ".join(pks), ", ".join(reserved_columns)
                )
            )

        column_definitions.update(
            {
                "score": float,
                "entity": int,
                "begin_offset": int,
                "end_offset": int,
            }
        )
        foreign_keys = [
            ("entity", "comprehend_entities", "id"),
        ]
        if len(pks) == 1:
            pk = pks[0]
            foreign_keys.append((pk, table, pk))
        db[output_table].create(column_definitions, foreign_keys=foreign_keys)

    # Build the SQL query
    sql = "select {} from {}".format(
        ", ".join(list(pks) + list(columns)),
        table,
    )
    where_clauses = []
    # Clause to skip previously processed rows:
    if db[done_table].exists():
        where_clauses.append(
            "({pks}) not in (select {pks} from {done_table})".format(
                pks=", ".join(pks),
                done_table=done_table,
            )
        )
    if where:
        where_clauses.append(where)
    if where_clauses:
        sql += " where " + " and ".join(where_clauses)

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
                concat = " ".join((row[column] or "") for column in columns)
                if should_strip_tags:
                    concat = strip_tags(concat)
                concat_utf8 = concat.encode("utf-8")
                if len(concat_utf8) > 5000:
                    concat_utf8 = concat_utf8[:5000]
                    # Truncate back to last whitespace to avoid risk of splitting a codepoint
                    concat_utf8 = concat_utf8.rsplit(None, 1)[0]
                texts.append(concat_utf8.decode("utf-8"))

            # Run the batch
            response = comprehend.batch_detect_entities(
                TextList=texts, LanguageCode="en"
            )
            if response.get("ErrorList"):
                # Match errors to documents
                errors_by_index = {
                    error["Index"]: error for error in response["ErrorList"]
                }
                for i, row in enumerate(chunk):
                    if i in errors_by_index:
                        click.echo(
                            "{}: Error: {}".format(
                                json.dumps({pk: row[pk] for pk in pks}),
                                json.dumps(errors_by_index[i]),
                            ),
                            err=True,
                        )

            results = response["ResultList"]
            # Match those to their primary keys and insert into output_table
            # we match on Index because we cannot guarantee that every document
            # has an item in ResultList, since there may have been errors
            results_by_index = {
                result["Index"]: result["Entities"] for result in results
            }
            to_insert = []
            for i, row in enumerate(chunk):
                pk_values = {pk: row[pk] for pk in pks}
                entities = results_by_index.get(i, [])
                if entities:
                    to_insert.extend(
                        [
                            dict(
                                **pk_values,
                                score=entity["Score"],
                                entity=entities_table.lookup(
                                    {
                                        "type": db["comprehend_entity_types"].lookup(
                                            {"value": entity["Type"]}
                                        ),
                                        "name": entity["Text"],
                                    }
                                ),
                                begin_offset=entity["BeginOffset"],
                                end_offset=entity["EndOffset"],
                            )
                            for entity in entities
                        ]
                    )
            if to_insert:
                db[output_table].insert_all(to_insert)
            db[done_table].insert_all(
                [{pk: row[pk] for pk in pks} for row in chunk],
                pk=pks,
                foreign_keys=[(pks[0], table, pks[0])] if len(pks) == 1 else [],
            )
