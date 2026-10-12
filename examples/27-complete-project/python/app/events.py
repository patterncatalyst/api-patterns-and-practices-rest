"""Ch21's background event-streaming path: a CloudEvents-enveloped
`BookingEvent` (`contracts/schemas/shipping.schema.json#/$defs/BookingEvent`)
published to the Kafka topic `shipping.bookings.lifecycle` — the exact
channel + message shape declared in
`contracts/asyncapi/shipping-events.yaml`. Fired once the async
confirmation operation (Ch10, see app/operations.py) actually completes,
not from the request thread that created the booking.

Uses confluent-kafka (idiomatic, librdkafka-backed Python producer) rather
than hand-rolling the Kafka wire protocol.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from confluent_kafka import Producer

from app.models import Booking, BookingEvent, BookingStatus
from app.ulid import generate_ulid

logger = logging.getLogger("ch27.events")

TOPIC = os.environ.get("BOOKING_EVENTS_TOPIC", "shipping.bookings.lifecycle")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

_producer: Producer | None = None


def _get_producer() -> Producer:
    global _producer
    if _producer is None:
        _producer = Producer({"bootstrap.servers": BOOTSTRAP_SERVERS})
    return _producer


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def publish_confirmed(confirmed: Booking, previous_status: BookingStatus) -> None:
    """Publish a `dev.patterncatalyst.shipping.booking.confirmed` CloudEvent
    describing `previous_status` -> CONFIRMED. Blocks (bounded, via
    `flush()`) until the broker acks the send. A failed publish must never
    surface as an error on the already-returned synchronous REST response
    — log and move on.
    """
    try:
        occurred_at = _now_utc()
        data = BookingEvent(
            bookingId=confirmed.id,
            status=BookingStatus.CONFIRMED,
            previousStatus=previous_status,
            origin=confirmed.origin,
            destination=confirmed.destination,
            occurredAt=occurred_at,
        )
        envelope = {
            "specversion": "1.0",
            "id": f"evt_{generate_ulid()}",
            "source": "/shipping/bookings",
            "type": "dev.patterncatalyst.shipping.booking.confirmed",
            "subject": confirmed.id,
            "time": occurred_at,
            "datacontenttype": "application/json",
            "data": data.model_dump(mode="json", exclude_none=True),
        }
        payload = json.dumps(envelope).encode("utf-8")

        producer = _get_producer()
        producer.produce(TOPIC, value=payload)
        remaining = producer.flush(10)
        if remaining > 0:
            logger.error("Kafka flush timed out with %d message(s) still in queue", remaining)
        else:
            logger.info("published BookingEvent for %s to %s", confirmed.id, TOPIC)
    except Exception:
        logger.exception("failed to publish BookingEvent to Kafka")
