from click.testing import CliRunner
from unittest.mock import call
from sqlite_comprehend.cli import cli
import sqlite_utils


def test_entities(mocker, tmpdir):
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
    boto3 = mocker.patch("boto3.client")
    boto3.return_value.batch_detect_entities.return_value = {
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
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["entities", db_path, "pages", "text"])
        assert result.exit_code == 0
        assert set(db.table_names()) == {
            "pages",
            "comprehend_entity_types",
            "comprehend_entities",
            "pages_comprehend_entities",
        }
        entities = list(
            db.query(
                """
        select
            pages_comprehend_entities.id as page_id,
            pages_comprehend_entities.score,
            pages_comprehend_entities.begin_offset,
            pages_comprehend_entities.end_offset,
            comprehend_entities.name as entity_name,
            comprehend_entity_types.value as entity_type
        from
            pages_comprehend_entities
            join comprehend_entities on pages_comprehend_entities.entity = comprehend_entities.id
            join comprehend_entity_types on comprehend_entities.type = comprehend_entity_types.id
        """
            )
        )
        assert entities == [
            {
                "page_id": 1,
                "score": 0.8,
                "begin_offset": 0,
                "end_offset": 5,
                "entity_name": "John Bob",
                "entity_type": "PERSON",
            },
            {
                "page_id": 2,
                "score": 0.8,
                "begin_offset": 0,
                "end_offset": 5,
                "entity_name": "Sandra X",
                "entity_type": "PERSON",
            },
        ]
        assert boto3.mock_calls == [
            call("comprehend"),
            call().batch_detect_entities(
                TextList=["John Bob", "Sandra X"], LanguageCode="en"
            ),
        ]
