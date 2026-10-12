package com.patterncatalyst.shipping.model;

/**
 * Local audit-trail shape — NOT part of the shared contract schema
 * (contracts/schemas/shipping.schema.json has no `DeletionAudit` def). A
 * soft-delete (`DELETE /bookings/{id}`) records one of these; a purge
 * (`DELETE /bookings/{id}/purge`) erases it along with the booking itself.
 * See README.md's "Soft delete vs. purge" section for why this rides along
 * as response HEADERS on the audit view rather than as extra fields on the
 * `Booking` body — the schema declares `additionalProperties: false` on
 * `Booking`, so a documented local shape has to live somewhere the
 * contract doesn't police.
 */
public record DeletionAudit(String deletedAt, String reason) {
}
