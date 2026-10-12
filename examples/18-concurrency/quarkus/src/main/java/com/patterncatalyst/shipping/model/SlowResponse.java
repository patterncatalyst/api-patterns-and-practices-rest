package com.patterncatalyst.shipping.model;

/**
 * The body `GET /io/slow` and `GET /io/slow-blocking` both return —
 * deliberately tiny, since this chapter is about HOW the delay is
 * implemented, not what shape comes back.
 *
 * {@code worker} is the name of the thread that produced the response, so a
 * caller can see directly which execution model served a given request: a
 * Vert.x event-loop thread for the non-blocking endpoint (a handful of
 * those threads serve every concurrent caller), or a Vert.x worker-pool
 * thread for the blocking one (one thread tied up per in-flight request).
 */
public record SlowResponse(long sleptMs, String worker) {
}
