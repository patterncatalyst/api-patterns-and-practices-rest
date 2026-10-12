package com.patterncatalyst.shipping;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

/**
 * Deterministic, fixed-size, in-memory "manifest" generator — the large
 * binary resource this chapter serves Range requests against.
 *
 * Each booking's manifest is a {@link #MANIFEST_SIZE_BYTES}-byte blob
 * derived purely from the booking id: block[0] = SHA-256(bookingId),
 * block[n] = SHA-256(block[n-1]), concatenated until the target size is
 * reached and truncated to it. Same id in, same bytes out, every time, with
 * no persistence — generated once per booking id and cached, so repeated
 * Range requests against the same manifest don't re-hash ~2 MiB on every
 * call. The two stacks are NOT required to produce byte-identical manifests
 * for the same id (each has its own booking store and ids); what matters
 * for Ch15's point is that EACH stack, independently, produces a
 * deterministic, known-size manifest that correctly serves Range requests
 * over it. Mirrors app/manifest.py in the Python stack conceptually (same
 * chaining idea), not byte-for-byte.
 */
public final class ManifestGenerator {

    /** ~2 MiB — comfortably in the "1-5 MiB" range the chapter targets. */
    public static final int MANIFEST_SIZE_BYTES = 2 * 1024 * 1024;

    private static final ConcurrentMap<String, byte[]> CACHE = new ConcurrentHashMap<>();

    private ManifestGenerator() {
    }

    public static byte[] forBooking(String bookingId) {
        return CACHE.computeIfAbsent(bookingId, ManifestGenerator::generate);
    }

    private static byte[] generate(String bookingId) {
        try {
            MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
            ByteArrayOutputStream out = new ByteArrayOutputStream(MANIFEST_SIZE_BYTES + 32);
            byte[] block = sha256.digest(bookingId.getBytes(StandardCharsets.UTF_8));
            while (out.size() < MANIFEST_SIZE_BYTES) {
                out.writeBytes(block);
                block = sha256.digest(block);
            }
            return Arrays.copyOf(out.toByteArray(), MANIFEST_SIZE_BYTES);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is a required JDK algorithm", e);
        }
    }
}
