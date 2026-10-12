package com.patterncatalyst.shipping.model;

/**
 * Local audit-trail shape — NOT part of the shared contract schema (Ch13).
 * A soft-delete (`DELETE /bookings/{id}`) records one of these; a purge
 * (`DELETE /bookings/{id}/purge`) erases it along with the booking itself.
 * Rides along as response HEADERS on the audit view rather than as extra
 * `Booking` fields, since the schema declares `additionalProperties: false`
 * on `Booking`.
 */
public record DeletionAudit(String deletedAt, String reason) {
}
