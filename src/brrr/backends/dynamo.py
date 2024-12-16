from __future__ import annotations

import typing

from ..store import CompareMismatch, MemKey, Store

if typing.TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

# The frame table layout is:
#
#   pk: MEMO_KEY
#   sk: "pending_returns"
#   parents: list[str]
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
        response = self.client.get_item(
            TableName=self.table_name,
            Key=self.key(key),
        )
        if "Item" not in response:
            raise KeyError(key)
        return response["Item"]["value"]["B"]


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

    def compare_and_set(self, key: MemKey, value: bytes, expected: bytes | None):
        ExpressionAttributeValues={":value": {"B": value}}
        if expected is None:
            ConditionExpression="attribute_not_exists(#value)"
        else:
            ExpressionAttributeValues[":expected"] = {"B": expected}
            ConditionExpression="#value = :expected"

        try:
            self.client.update_item(
                TableName=self.table_name,
                Key=self.key(key),
                UpdateExpression="SET #value = :value",
                ExpressionAttributeNames={"#value": "value"},
                ExpressionAttributeValues=ExpressionAttributeValues,
                ConditionExpression=ConditionExpression,
            )
        except self.client.exceptions.ConditionalCheckFailedException:
            raise CompareMismatch

    def compare_and_delete(self, key: MemKey, expected: bytes):
        try:
            self.client.delete_item(
                TableName=self.table_name,
                Key=self.key(key),
                ConditionExpression="attribute_exists(#value) AND #value = :expected",
                # value is a reserved word in DynamoDB
                ExpressionAttributeNames={"#value": "value"},
                ExpressionAttributeValues={":expected": {"B": expected}},
            )
        except self.client.exceptions.ConditionalCheckFailedException:
            raise CompareMismatch

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
