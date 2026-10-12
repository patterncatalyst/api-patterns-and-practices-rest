package com.patterncatalyst.shipping.model;

/** `#/$defs/Problem` — RFC 9457 Problem Details (application/problem+json). */
public record Problem(String type, String title, int status, String detail, String instance) {

    public Problem(String title, int status, String detail) {
        this("about:blank", title, status, detail, null);
    }
}
