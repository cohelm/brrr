from __future__ import annotations

import os
import typing

from ..store import MemKey, Store

if typing.TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

# The frame table layout is:
#
#   pk: FRAME_KEY
#   sk: FRAME_KEY
#   parent: The parent frame key
#   memo: The memo key
#
# OR
#
#   pk: FRAME_KEY
#   sk: A child's frame key
#
# OR
#
#   pk: MEMO_KEY
#   sk: "call"
#   task: The task name
#   argv: bytes (pickled)
#
# OR
#
#   pk: MEMO_KEY
#   sk: "value"
#   value: bytes (pickled)
#
# TODO It is possible we'll add versioning in there as pk or somethin
class DynamoDbMemStore(Store):
    client: DynamoDBClient
    table_name: str

    def key(self, mem_key: MemKey) -> dict:
        return {
            "pk": {"S": mem_key.id},
            "sk": {"S": mem_key.type}
        }

    def __init__(self, client: DynamoDBClient, table_name: str):
        self.client = client
        self.table_name = table_name

    def __contains__(self, key: MemKey):
        return "Item" in self.client.get_item(
            TableName=self.table_name,
            Key=self.key(key),
        )

    def __getitem__(self, key: MemKey) -> bytes:
        return self.client.get_item(
            TableName=self.table_name,
            Key=self.key(key),
        )["Item"]["value"]["B"]

    def __setitem__(self, key: MemKey, value: bytes):
        self.client.put_item(
            TableName=self.table_name,
            Item={
                **self.key(key),
                "value": {"B": value}
            }
        )

    def __delitem__(self, key: MemKey):
        self.client.delete_item(
            TableName=self.table_name,
            Key=self.key(key),
        )

    def __iter__(self):
        raise NotImplementedError

    def __len__(self):
        raise NotImplementedError

    def create_table(self):
        try:
            self.client.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {
                        "AttributeName": "pk",
                        "KeyType": "HASH"
                    },
                    {
                        "AttributeName": "sk",
                        "KeyType": "RANGE"
                    }
                ],
                AttributeDefinitions=[
                    {
                        "AttributeName": "pk",
                        "AttributeType": "S"
                    },
                    {
                        "AttributeName": "sk",
                        "AttributeType": "S"
                    }
                ],
                # TODO make this configurable? Should this method even exist?
                ProvisionedThroughput={
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                }
            )
        except self.client.exceptions.ResourceInUseException:
            pass
