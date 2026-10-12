package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.BookingStatus;
import com.patterncatalyst.shipping.model.JobDefinition;
import com.patterncatalyst.shipping.model.Operation;
import com.patterncatalyst.shipping.model.OperationStatus;

import jakarta.annotation.PreDestroy;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;

import org.jboss.logging.Logger;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Server-owned state for the single {@code manifest-reconcile} job: the
 * schedule/definition (configure, server-owned) plus the run records a
 * client or the server's own scheduler produce (execute). This is the
 * configure-vs-execute split the chapter is about:
 *
 * <ul>
 *   <li>{@link #configure} — a client PUTs a schedule
 *       ({@code enabled}/{@code intervalSeconds}); the client never drives
 *       an individual run.</li>
 *   <li>{@link #triggerRun} — either the periodic {@link #tick()} (fired by
 *       {@code scheduler} at the CONFIGURED interval) or an explicit "run
 *       now" request creates a new {@link Operation}-shaped run record and
 *       executes it asynchronously through PENDING -&gt; RUNNING -&gt;
 *       SUCCEEDED/FAILED.</li>
 * </ul>
 *
 * <p>The "reconcile" work itself is deliberately trivial and fast (a scan
 * of {@link BookingStore#listVisible()}) — the point of this chapter is the
 * rerunnable-job *protocol*, not a real manifest-reconciliation engine.
 * {@link #WORK_DELAY_MS} keeps a run observably RUNNING for a moment (so a
 * poll immediately after "run now" reliably sees it mid-flight) while
 * staying well inside verify.sh's poll budget.
 */
@ApplicationScoped
public class JobStore {

    public static final String JOB_ID = "manifest-reconcile";

    /** Deterministic, short "work" duration for a single run — long enough
     * that RUNNING is observable, short enough to keep CI bounded. */
    public static final long WORK_DELAY_MS = 300;

    private static final Logger LOG = Logger.getLogger(JobStore.class);

    @Inject
    BookingStore bookingStore;

    private final AtomicReference<JobDefinitionRecord> definition = new AtomicReference<>();
    private final Map<String, RunRecord> runs = Collections.synchronizedMap(new LinkedHashMap<>());

    private final ScheduledExecutorService scheduler =
            Executors.newScheduledThreadPool(2, runnable -> {
                Thread thread = new Thread(runnable, "ch11-job-scheduler");
                thread.setDaemon(true);
                return thread;
            });

    /** The currently-armed periodic tick, re-armed every time {@link
     * #configure} changes the interval. Null until the job is configured
     * for the first time — no definition means nothing to execute. */
    private volatile ScheduledFuture<?> tickFuture;

    public record ConfigureResult(JobDefinition definition, boolean created) {
    }

    /**
     * Upserts the job definition (server-owned schedule) and re-arms the
     * periodic ticker at the new {@code intervalSeconds} — this is what
     * makes "the client configures the schedule" literally true: the
     * scheduler's cadence comes from the configured value, not a hardcoded
     * constant.
     */
    public synchronized ConfigureResult configure(boolean enabled, int intervalSeconds) {
        JobDefinitionRecord existing = definition.get();
        boolean created = existing == null;
        String now = nowUtc();
        String createdAt = created ? now : existing.createdAt;
        JobDefinitionRecord updated = new JobDefinitionRecord(enabled, intervalSeconds, createdAt, now);
        definition.set(updated);
        rearmTick(intervalSeconds);
        return new ConfigureResult(updated.toJobDefinition(), created);
    }

    public JobDefinition getDefinition() {
        JobDefinitionRecord record = definition.get();
        return record == null ? null : record.toJobDefinition();
    }

    /** "Run now": creates a run record and executes it asynchronously,
     * independent of the periodic scheduler. Returns null if the job has
     * never been configured. */
    public Operation triggerRun() {
        if (definition.get() == null) {
            return null;
        }
        return startRun();
    }

    public Operation getRun(String runId) {
        RunRecord record = runs.get(runId);
        return record == null ? null : record.toOperation();
    }

    /** Newest-first, per the run collection's documented ordering. */
    public List<Operation> listRuns() {
        List<Operation> result = new ArrayList<>();
        synchronized (runs) {
            for (RunRecord record : runs.values()) {
                result.add(record.toOperation());
            }
        }
        Collections.reverse(result);
        return result;
    }

    // ------------------------------------------------------------------
    // Scheduler
    // ------------------------------------------------------------------

    private void rearmTick(int intervalSeconds) {
        if (tickFuture != null) {
            tickFuture.cancel(false);
        }
        tickFuture = scheduler.scheduleAtFixedRate(
                this::tick, intervalSeconds, intervalSeconds, TimeUnit.SECONDS);
    }

    /** Fired by the scheduler every {@code intervalSeconds}. Only starts an
     * automatic run while the job is enabled — disabling it stops new runs
     * from being produced without un-configuring the job entirely. */
    private void tick() {
        JobDefinitionRecord def = definition.get();
        if (def == null || !def.enabled) {
            return;
        }
        LOG.infof("ch11: scheduler tick firing an automatic %s run", JOB_ID);
        startRun();
    }

    private Operation startRun() {
        // "op_" prefix (not "run_"): this run record reuses
        // #/$defs/Operation verbatim, including its id pattern
        // (^op_[0-9A-HJKMNP-TV-Z]{26}$) — see model/Operation.java's javadoc.
        String runId = "op_" + Ulid.generate();
        RunRecord record = new RunRecord(runId, nowUtc());
        runs.put(runId, record);
        scheduler.execute(() -> executeRun(record));
        return record.toOperation();
    }

    /** The trivial "reconcile manifests against bookings" work: scan the
     * booking store, then report success. A real implementation would
     * compare each booking's manifest against carrier data; this chapter's
     * point is the job-lifecycle protocol around that work, not the work
     * itself. */
    private void executeRun(RunRecord record) {
        record.status.set(OperationStatus.RUNNING);
        int pendingCount = (int) bookingStore.listVisible().stream()
                .filter(b -> b.status() == BookingStatus.PENDING)
                .count();
        LOG.infof("ch11: run %s reconciling %d PENDING booking(s)", record.id, pendingCount);
        try {
            Thread.sleep(WORK_DELAY_MS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        record.completedAt = nowUtc();
        record.status.set(OperationStatus.SUCCEEDED);
    }

    @PreDestroy
    void shutdown() {
        scheduler.shutdownNow();
    }

    private static String nowUtc() {
        return Instant.now().truncatedTo(ChronoUnit.SECONDS).toString();
    }

    private static final class JobDefinitionRecord {
        final boolean enabled;
        final int intervalSeconds;
        final String createdAt;
        final String updatedAt;

        JobDefinitionRecord(boolean enabled, int intervalSeconds, String createdAt, String updatedAt) {
            this.enabled = enabled;
            this.intervalSeconds = intervalSeconds;
            this.createdAt = createdAt;
            this.updatedAt = updatedAt;
        }

        JobDefinition toJobDefinition() {
            return new JobDefinition(JOB_ID, enabled, intervalSeconds, createdAt, updatedAt);
        }
    }

    /** Mutable internal record; {@link Operation} (the type serialized over
     * the wire) stays an immutable snapshot taken via {@link #toOperation()}. */
    private static final class RunRecord {
        final String id;
        final String createdAt;
        final AtomicReference<OperationStatus> status = new AtomicReference<>(OperationStatus.PENDING);
        volatile String completedAt;

        RunRecord(String id, String createdAt) {
            this.id = id;
            this.createdAt = createdAt;
        }

        Operation toOperation() {
            return new Operation(id, status.get(), createdAt, completedAt, null, null);
        }
    }
}
