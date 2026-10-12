package com.patterncatalyst.shipping;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingStatus;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.eclipse.microprofile.reactive.messaging.Channel;
import org.eclipse.microprofile.reactive.messaging.Emitter;
import org.jboss.logging.Logger;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * The event side of this chapter's "one service, two protocols" thesis: a
 * CloudEvents-enveloped `BookingEvent` (`contracts/schemas/shipping.schema.json#/$defs/BookingEvent`)
 * published to the Kafka topic `shipping.bookings.lifecycle` — the exact
 * channel + message shape declared in
 * `contracts/asyncapi/shipping-events.yaml`. The envelope shape mirrors
 * `contracts/cloudevents/booking-confirmed.example.json` byte-for-byte:
 * `specversion`, `id`, `source`, `type`, `subject`, `time`,
 * `datacontenttype`, `data`.
 *
 * Uses the SmallRye Reactive Messaging Kafka connector (idiomatic Quarkus
 * emit path) rather than a hand-rolled KafkaProducer.
 */
@ApplicationScoped
public class BookingEventPublisher {

    private static final Logger LOG = Logger.getLogger(BookingEventPublisher.class);

    @Inject
    @Channel("booking-events")
    Emitter<String> emitter;

    @Inject
    ObjectMapper mapper;

    /**
     * Publish a `dev.patterncatalyst.shipping.booking.confirmed` CloudEvent
     * whose `data` is a `BookingEvent` describing the PENDING -> CONFIRMED
     * transition. Blocks (bounded) until the broker acks the send so a
     * caller running this off the request thread (see BookingResource) knows
     * the event actually landed before moving on.
     */
    public void publishConfirmed(Booking confirmed, BookingStatus previousStatus) {
        try {
            String occurredAt = nowUtc();

            Map<String, Object> data = new LinkedHashMap<>();
            data.put("bookingId", confirmed.id());
            data.put("status", confirmed.status().name());
            data.put("previousStatus", previousStatus == null ? null : previousStatus.name());
            data.put("origin", confirmed.origin());
            data.put("destination", confirmed.destination());
            data.put("occurredAt", occurredAt);

            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("specversion", "1.0");
            envelope.put("id", "evt_" + Ulid.generate());
            envelope.put("source", "/shipping/bookings");
            envelope.put("type", "dev.patterncatalyst.shipping.booking.confirmed");
            envelope.put("subject", confirmed.id());
            envelope.put("time", occurredAt);
            envelope.put("datacontenttype", "application/json");
            envelope.put("data", data);

            String json = mapper.writeValueAsString(envelope);
            emitter.send(json).toCompletableFuture().get(10, TimeUnit.SECONDS);
            LOG.infof("published BookingEvent for %s to shipping.bookings.lifecycle", confirmed.id());
        } catch (Exception e) {
            // A failed background publish must never surface as a 5xx on the
            // already-returned synchronous REST response — log and move on.
            LOG.error("failed to publish BookingEvent to Kafka", e);
        }
    }

    private static String nowUtc() {
        return Instant.now().truncatedTo(ChronoUnit.SECONDS).toString();
    }
}
