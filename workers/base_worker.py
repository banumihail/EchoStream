"""
Base Worker class for EchoStream
Handles RabbitMQ connection and message consumption
"""
import pika
import json
import sys
import os

# Workers run head-less on Windows, where stdout defaults to a legacy code page
# (cp1252) that cannot encode emoji / CJK / math-italic characters common in
# video titles. Without this, a single print() of an exotic filename raises
# UnicodeEncodeError and fails the whole task before processing even starts.
# Force UTF-8 with errors="replace" so logging can never crash a worker.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.rabbitmq_client import RabbitMQClient


class BaseWorker:
    """
    Base class for all EchoStream workers
    Handles RabbitMQ connection and provides process_task method to override
    """

    def __init__(self, queue_name: str, worker_name: str = "Worker", worker_key: str = None):
        self.queue_name = queue_name
        self.worker_name = worker_name
        self.worker_key = worker_key  # ES field prefix, e.g. "asr", "ner"
        self.client = RabbitMQClient()

    def process_task(self, task_data: dict):
        """
        Override this method in child classes to implement specific processing logic

        Args:
            task_data: Dictionary containing task information from RabbitMQ
        """
        raise NotImplementedError("Subclasses must implement process_task()")

    def callback(self, ch, method, properties, body):
        """
        Called when a message is received from RabbitMQ

        Args:
            ch: Channel
            method: Method
            properties: Properties
            body: Message body (JSON string)
        """
        try:
            # Parse message
            task_data = json.loads(body)
            task_id = task_data.get("task_id", "unknown")

            print(f"\n[{self.worker_name}] Received task: {task_id}")
            print(f"  Filename: {task_data.get('filename')}")

            # Process the task
            self.process_task(task_data)

            # Acknowledge successful processing
            ch.basic_ack(delivery_tag=method.delivery_tag)
            print(f"[{self.worker_name}] Task {task_id} completed successfully")

        except Exception as e:
            print(f"[{self.worker_name}] Error processing task: {e}")
            import traceback
            traceback.print_exc()
            # Try to mark the worker as errored in ES so the UI doesn't stay stuck
            try:
                task_data_err = json.loads(body) if isinstance(body, (bytes, str)) else {}
                task_id_err = task_data_err.get("task_id")
                if task_id_err and self.worker_key and hasattr(self, 'get_es_client'):
                    es = self.get_es_client()
                    es.update_worker_status(task_id_err, self.worker_key, "error")
            except Exception:
                pass
            # Negative acknowledgment - do not requeue to prevent infinite loops
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start(self):
        """Start consuming messages from the queue"""
        try:
            print(f"\n{'=' * 60}")
            print(f"{self.worker_name} starting...")
            print(f"Queue: {self.queue_name}")
            print(f"{'=' * 60}\n")

            # Connect to RabbitMQ
            self.client.connect()
            self.client.declare_queue(self.queue_name)

            # Set QoS - process one message at a time
            self.client.channel.basic_qos(prefetch_count=1)

            # Start consuming
            self.client.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=self.callback,
                auto_ack=False  # Manual acknowledgment
            )

            print(f"[{self.worker_name}] Waiting for messages...")
            print("Press CTRL+C to exit\n")

            self.client.channel.start_consuming()

        except KeyboardInterrupt:
            print(f"\n[{self.worker_name}] Shutting down...")
            self.client.close()

        except Exception as e:
            print(f"[{self.worker_name}] Fatal error: {e}")
            self.client.close()
