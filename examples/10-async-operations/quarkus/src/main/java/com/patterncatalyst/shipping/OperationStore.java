package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Operation;
import com.patterncatalyst.shipping.model.OperationStatus;
import com.patterncatalyst.shipping.model.Problem;

import jakarta.annotation.PreDestroy;
import jakarta.enterprise.context.ApplicationScoped;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/**
 * In-memory store + background worker for long-running confirmation
 * Operations (Ch10). A small daemon-thread scheduled executor stands in for
 * a real job queue / saga orchestrator — the point of this chapter is the
 * 202 -&gt; poll -&gt; 303 *protocol*, not a production async runtime.
 *
 * <p>Deterministic and SHORT on purpose: {@link #CONFIRMATION_DELAY_MS}
 * keeps verify.sh (and CI) bounded while still being long enough that a
 * poll immediately after the 202 reliably observes RUNNING rather than a
 * race to SUCCEEDED.
 */
@ApplicationScoped
public class OperationStore {

    public static final long CONFIRMATION_DELAY_MS = 2000;

    private final Map<String, OperationRecord> operations = new ConcurrentHashMap<>();
    private final ScheduledExecutorService scheduler =
            Executors.newScheduledThreadPool(2, runnable -> {
                Thread thread = new Thread(runnable, "ch10-operation-worker");
                thread.setDaemon(true);
                return thread;
            });

    /**
     * Creates a RUNNING operation for confirming {@code bookingId} and
     * schedules the worker to complete it after {@link #CONFIRMATION_DELAY_MS}.
     */
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

    /**
     * Cancels a still-PENDING/RUNNING operation: the worker's delayed
     * completion checks {@code cancelled} under the same per-record lock
     * before mutating anything, so a cancel that wins the race leaves the
     * booking PENDING. Returns false if the operation is unknown or already
     * terminal (SUCCEEDED/FAILED) — the caller treats DELETE as idempotent
     * either way.
     */
    public boolean cancel(String opId) {
        OperationRecord record = operations.get(opId);
        if (record == null) {
            return false;
        }
        synchronized (record) {
            OperationStatus current = record.status.get();
            if (current != OperationStatus.PENDING && current != OperationStatus.RUNNING) {
                return false;
            }
            record.cancelled.set(true);
            record.status.set(OperationStatus.FAILED);
            record.completedAt = nowUtc();
            record.error = new Problem("Operation cancelled", 499,
                    "Cancelled by client request before completion");
        }
        return true;
    }

    private void completeConfirmation(String opId, BookingStore bookingStore) {
        OperationRecord record = operations.get(opId);
        if (record == null) {
            return;
        }
        synchronized (record) {
            if (record.cancelled.get()) {
                return; // cancel() already finalized this operation as FAILED.
            }
            bookingStore.confirm(record.bookingId);
            record.status.set(OperationStatus.SUCCEEDED);
            record.completedAt = nowUtc();
            record.resource = "/bookings/" + record.bookingId;
        }
    }

    @PreDestroy
    void shutdown() {
        scheduler.shutdownNow();
    }

    private static String nowUtc() {
        return Instant.now().truncatedTo(ChronoUnit.SECONDS).toString();
    }

    /**
     * Mutable internal record; {@link Operation} (the type serialized over
     * the wire) stays an immutable snapshot taken via {@link #toOperation()}.
     */
    private static final class OperationRecord {
        final String id;
        final String bookingId;
        final String createdAt;
        final AtomicReference<OperationStatus> status = new AtomicReference<>(OperationStatus.RUNNING);
        final AtomicBoolean cancelled = new AtomicBoolean(false);
        volatile String completedAt;
        volatile String resource;
        volatile Problem error;

        OperationRecord(String id, String bookingId, String createdAt) {
            this.id = id;
            this.bookingId = bookingId;
            this.createdAt = createdAt;
        }

        Operation toOperation() {
            return new Operation(id, status.get(), createdAt, completedAt, resource, error);
        }
    }
}
