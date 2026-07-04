"""
RabbitMQ 任务队列 — 异步调研任务分发
Producer: API 层提交任务到队列，立即返回
Consumer: Worker 消费队列，执行 Graph 流程
"""
import json
import os
import pika
from app.core.logging import logger

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE_NAME = "research_tasks"


def get_connection():
    params = pika.URLParameters(RABBITMQ_URL)
    params.heartbeat = 600
    params.blocked_connection_timeout = 300
    return pika.BlockingConnection(params)


def publish_task(session_id: str, topic: str, max_iterations: int = 3) -> None:
    """发布调研任务到队列（Producer）"""
    try:
        conn = get_connection()
        channel = conn.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        message = json.dumps({
            "session_id": session_id,
            "topic": topic,
            "max_iterations": max_iterations,
        })
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=message,
            properties=pika.BasicProperties(delivery_mode=2),  # 消息持久化
        )
        logger.info(f"任务入队: {session_id}")
        conn.close()
    except Exception as e:
        logger.error(f"RabbitMQ 发布失败: {e}")


def start_consumer(callback):
    """启动任务消费者（Consumer）"""
    try:
        conn = get_connection()
        channel = conn.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_qos(prefetch_count=1)  # 每次只取 1 条，公平分发

        def on_message(ch, method, properties, body):
            try:
                task = json.loads(body)
                logger.info(f"消费任务: {task.get('session_id')}")
                callback(task)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                logger.error(f"任务执行失败: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)
        logger.info("RabbitMQ Consumer 启动，等待任务...")
        channel.start_consuming()
    except Exception as e:
        logger.error(f"RabbitMQ 连接失败: {e}")
