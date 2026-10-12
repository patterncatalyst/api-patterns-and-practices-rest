package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.SlowResponse;

import io.smallrye.mutiny.Uni;

import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

import org.jboss.resteasy.reactive.RestQuery;

import java.time.Duration;

/**
 * Ch18's whole point: two ways to implement "call a slow downstream
 * dependency and return its result," and the very different concurrency
 * behavior each one produces under load.
 *
 * <ul>
 *   <li>{@link #slow} — the idiomatic REACTIVE answer. Returns a Mutiny
 *       {@link Uni} whose emission is delayed by a Vert.x timer
 *       ({@code onItem().delayIt().by(...)}), not a {@code Thread.sleep()}.
 *       No thread sits blocked for the duration of the simulated I/O — the
 *       request handling thread returns to the event loop immediately, and
 *       a timer callback resumes the response later. Quarkus REST dispatches
 *       any resource method returning {@code Uni}/{@code Multi} on the
 *       Vert.x event-loop threads (a small, fixed pool — by default one per
 *       CPU core), so N concurrent callers of this endpoint are served by
 *       those same few threads, not N threads.</li>
 *
 *   <li>{@link #slowBlocking} — the NAIVE answer, kept here only as a
 *       contrast. It returns a plain {@code SlowResponse}, not a
 *       {@code Uni}, so Quarkus REST dispatches it to the Vert.x WORKER
 *       thread pool and calls {@code Thread.sleep()} there — one worker
 *       thread tied up for the full simulated I/O duration, per in-flight
 *       request. That pool is finite ({@code quarkus.thread-pool.max-threads});
 *       once every worker is asleep, the next request queues
 *       behind them instead of running concurrently. A virtual-threads
 *       {@code @RunOnVirtualThread} method would dodge this specific
 *       problem (the JVM parks the virtual thread instead of a carrier
 *       thread), but still performs a real, if cheap, context switch per
 *       call — the fully non-blocking {@link #slow} above ties up nothing
 *       at all while waiting. See README.md for how to flip the worker
 *       pool down to 1 and watch this endpoint serialize.</li>
 * </ul>
 */
@Path("/io")
public class IoResource {

    @GET
    @Path("/slow")
    @Produces(MediaType.APPLICATION_JSON)
    public Uni<SlowResponse> slow(@RestQuery("ms") @DefaultValue("200") long ms) {
        return Uni.createFrom()
                .item(() -> new SlowResponse(ms, Thread.currentThread().getName()))
                .onItem().delayIt().by(Duration.ofMillis(ms));
    }

    @GET
    @Path("/slow-blocking")
    @Produces(MediaType.APPLICATION_JSON)
    public SlowResponse slowBlocking(@RestQuery("ms") @DefaultValue("200") long ms) throws InterruptedException {
        Thread.sleep(ms);
        return new SlowResponse(ms, Thread.currentThread().getName());
    }
}
