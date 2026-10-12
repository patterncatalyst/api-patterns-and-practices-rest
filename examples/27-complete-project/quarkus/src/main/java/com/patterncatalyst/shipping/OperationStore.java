package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingStatus;
import com.patterncatalyst.shipping.model.Operation;
import com.patterncatalyst.shipping.model.OperationStatus;

import jakarta.annotation.PreDestroy;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Ch10: in-memory store + background worker for long-running confirmation
 * Operations. A small daemon-thread scheduled executor stands in for a real
 * job queue / saga orchestrator — once the confirmation completes, it
 * flips the booking to CONFIRMED (BookingStore) and publishes the Ch21
 * CloudEvent (BookingEventPublisher), tying the async protocol and the
 * background event-streaming path together.
 *
 * <p>Deterministic and SHORT on purpose: {@link #CONFIRMATION_DELAY_MS}
 * keeps verify.sh (and CI) bounded while still being long enough that a
 * poll immediately after the 202 reliably observes RUNNING.
 */
@ApplicationScoped
public class OperationStore {

    public static final long CONFIRMATION_DELAY_MS = 1500;

    @Inject
    BookingEventPublisher eventPublisher;

    private final Map<String, OperationRecord> operations = new ConcurrentHashMap<>();
    private final ScheduledExecutorService scheduler =
            Executors.newScheduledThreadPool(2, runnable -> {
                Thread thread = new Thread(runnable, "ch27-operation-worker");
                thread.setDaemon(true);
                return thread;
            });

    public Operation startConfirmation(String opId, String bookingId, BookingStore bookingStore) {
        OperationRecord record = new OperationRecord(opId, bookingId, nowUtc());
        operations.put(opId, record);
        scheduler.schedule(() -> completeConfirmation(opId, bookingStore),
                CONFIRMATION_DELAY_MS, TimeUnit.MILLISECONDS);
        return record.toOperation();
    }

    public Operation get(String opId) {
        OperationRecord record = operations.get(opId);
        return record == null ? null : record.toOperation();
    }

    private void completeConfirmation(String opId, BookingStore bookingStore) {
        OperationRecord record = operations.get(opId);
        if (record == null) {
            return;
        }
        synchronized (record) {
            Booking confirmed = bookingStore.confirm(record.bookingId);
            record.status.set(OperationStatus.SUCCEEDED);
            record.completedAt = nowUtc();
            record.resource = "/bookings/" + record.bookingId;
            if (confirmed != null && confirmed.status() == BookingStatus.CONFIRMED) {
                eventPublisher.publishConfirmed(confirmed, BookingStatus.PENDING);
            }
        }
    }

    @PreDestroy
    void shutdown() {
        scheduler.shutdownNow();
    }

    private static String nowUtc() {
        return Instant.now().truncatedTo(ChronoUnit.SECONDS).toString();
    }

    private static final class OperationRecord {
        final String id;
        final String bookingId;
        final String createdAt;
        final AtomicReference<OperationStatus> status = new AtomicReference<>(OperationStatus.RUNNING);
        volatile String completedAt;
        volatile String resource;

        OperationRecord(String id, String bookingId, String createdAt) {
            this.id = id;
            this.bookingId = bookingId;
            this.createdAt = createdAt;
        }

        Operation toOperation() {
            return new Operation(id, status.get(), createdAt, completedAt, resource, null);
        }
    }
}
