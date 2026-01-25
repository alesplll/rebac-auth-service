"""Kafka consumer for cache invalidation."""
import json
import logging
from confluent_kafka import Consumer
from ..cache.redis_cache import RedisDecisionCache
from ..types import Tuple

logger = logging.getLogger(__name__)

class CacheInvalidationConsumer:
    """Consumes auth-change events and invalidates Redis cache."""

    def __init__(self, bootstrap_servers: str = "localhost:9092", 
                 topic: str = "auth-changes", 
                 redis_cache: RedisDecisionCache = None):
        self.consumer = Consumer({
            'bootstrap.servers': bootstrap_servers,
            'group.id': 'cache-invalidator',
            'auto.offset.reset': 'earliest',
        })
        self.consumer.subscribe([topic])
        self.redis_cache = redis_cache
        logger.info(f"Cache invalidation consumer started: {topic}")

    def run(self):
        """Start consuming events."""
        try:
            while True:
                msg = self.consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue

                event = json.loads(msg.value().decode('utf-8'))
                self._handle_event(event)
        finally:
            self.consumer.close()

    def _handle_event(self, event: dict):
        """Process single audit event."""
        event_type = event.get("event_type")
        if event_type != "tuple_written":
            return

        tuple_data = event["tuple"]
        invalidation_hints = event.get("invalidation_hints", [])

        for pattern in invalidation_hints:
            if self.redis_cache:
                self.redis_cache._client.delete(pattern)
                logger.info(f"Cache invalidated: {pattern}")

