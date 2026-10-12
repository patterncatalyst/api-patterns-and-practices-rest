package com.patterncatalyst.shipping;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Arrays;

/**
 * Minimal ULID generator (Crockford Base32, 26 chars): 48-bit timestamp (ms
 * since epoch, 10 chars) + 80-bit randomness (16 chars). Deliberately
 * dependency-free so this chapter's Containerfile stays small — a real
 * project would pull a vetted ULID library, but the shared schema only
 * cares that `bkg_`/`crg_` ids match
 * `^[0-9A-HJKMNP-TV-Z]{26}$` (Crockford base32: no I, L, O, U).
 */
public final class Ulid {

    private static final char[] ENCODING = "0123456789ABCDEFGHJKMNPQRSTVWXYZ".toCharArray();
    private static final SecureRandom RANDOM = new SecureRandom();

    private Ulid() {
    }

    /** Returns a 26-char Crockford-Base32 ULID string (no prefix). */
    public static String generate() {
        long timestamp = Instant.now().toEpochMilli();
        byte[] randomness = new byte[10];
        RANDOM.nextBytes(randomness);
        return encodeTime(timestamp) + encodeRandom(randomness);
    }

    private static String encodeTime(long timestamp) {
        char[] chars = new char[10];
        long value = timestamp;
        for (int i = 9; i >= 0; i--) {
            chars[i] = ENCODING[(int) (value & 0x1F)];
            value >>>= 5;
        }
        return new String(chars);
    }

    private static String encodeRandom(byte[] randomness) {
        long chunk1 = 0;
        for (int i = 0; i < 5; i++) {
            chunk1 = (chunk1 << 8) | (randomness[i] & 0xFF);
        }
        long chunk2 = 0;
        for (int i = 5; i < 10; i++) {
            chunk2 = (chunk2 << 8) | (randomness[i] & 0xFF);
        }
        StringBuilder sb = new StringBuilder(16);
        appendBase32(sb, chunk1, 8);
        appendBase32(sb, chunk2, 8);
        return sb.toString();
    }

    private static void appendBase32(StringBuilder sb, long value, int numChars) {
        char[] chars = new char[numChars];
        long v = value;
        for (int i = numChars - 1; i >= 0; i--) {
            chars[i] = ENCODING[(int) (v & 0x1F)];
            v >>>= 5;
        }
        sb.append(chars);
    }

    /**
     * A deterministic, non-random "ULID-shaped" id derived from {@code seed}
     * — same seed in, same 26-char Crockford string out, every time.
     *
     * Used by PUT (full replace), NOT by POST: an idempotent replace must
     * converge on the SAME resource state (including sub-resource ids like
     * Cargo.id) when called twice with the same body, whereas a create must
     * mint a genuinely new id every call. Seeding on "{bookingId}:{index}"
     * gives each cargo slot in a given booking's replace a stable identity
     * across repeated identical PUTs, without needing real persistence.
     */
    public static String deterministic(String seed) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(seed.getBytes(StandardCharsets.UTF_8));
            // 26 Crockford chars encode 130 bits; 17 bytes (136 bits) is the
            // smallest whole number of hash bytes that covers that.
            byte[] truncated = Arrays.copyOf(hash, 17);
            BigInteger value = new BigInteger(1, truncated);
            return encodeBigInteger(value, 26);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is a required JDK algorithm", e);
        }
    }

    private static String encodeBigInteger(BigInteger value, int numChars) {
        char[] chars = new char[numChars];
        BigInteger v = value;
        BigInteger mask = BigInteger.valueOf(0x1F);
        for (int i = numChars - 1; i >= 0; i--) {
            chars[i] = ENCODING[v.and(mask).intValue()];
            v = v.shiftRight(5);
        }
        return new String(chars);
    }
}
