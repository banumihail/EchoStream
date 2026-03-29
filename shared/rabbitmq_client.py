import pika
import json
from typing import Dict, Any


class RabbitMQClient:
    """
    Shared RabbitMQ client for EchoStream
    Handles connection and basic operations for both producer (API) and consumer (Workers)
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5672,
        username: str = "guest",
        password: str = "guest"
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.connection = None
        self.channel = None

    def connect(self):
        """Establish connection to RabbitMQ"""
        credentials = pika.PlainCredentials(self.username, self.password)
        parameters = pika.ConnectionParameters(
            host=self.host,
            port=self.port,
            credentials=credentials
        )
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        print(f"[OK] Connected to RabbitMQ at {self.host}:{self.port}")

    def declare_queue(self, queue_name: str, durable: bool = True):
        """Declare a queue (creates it if it doesn't exist)"""
        self.channel.queue_declare(queue=queue_name, durable=durable)
        print(f"[OK] Queue '{queue_name}' declared")

    def publish_message(self, queue_name: str, message: Dict[str, Any]):
        """
        Publish a message to a queue

        Args:
            queue_name: Name of the queue
            message: Dictionary to send (will be converted to JSON)
        """
        self.channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
            )
        )
        print(f"[OK] Message published to '{queue_name}'")

    def close(self):
        """Close connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            print("[OK] RabbitMQ connection closed")
