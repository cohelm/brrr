from __future__ import annotations

import typing

from ..queue import Queue, Message, QueueInfo, QueueIsEmpty

if typing.TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient

class SqsQueue(Queue):
    def __init__(self, client: SQSClient, url: str):
        self.client = client
        self.url = url

    def put(self, message: str):
        self.client.send_message(
            QueueUrl=self.url,
            MessageBody=message
        )

    def get_message(self) -> Message:
        response = self.client.receive_message(
            QueueUrl=self.url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=self.recv_block_secs,
        )

        if "Messages" not in response:
            raise QueueIsEmpty

        return Message(response["Messages"][0]["Body"], response["Messages"][0]["ReceiptHandle"])

    def delete_message(self, receipt_handle: str):
        self.client.delete_message(
            QueueUrl=self.url,
            ReceiptHandle=receipt_handle
        )

    def set_message_timeout(self, receipt_handle, seconds):
        self.client.change_message_visibility(
            QueueUrl=self.url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=seconds
        )

    def get_info(self):
        response = self.client.get_queue_attributes(
            QueueUrl=self.url,
            AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
        )
        return QueueInfo(
            num_messages=int(response["Attributes"]["ApproximateNumberOfMessages"]),
            num_inflight_messages=int(response["Attributes"]["ApproximateNumberOfMessagesNotVisible"])
        )
