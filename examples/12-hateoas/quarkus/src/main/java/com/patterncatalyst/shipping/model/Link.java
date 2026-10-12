package com.patterncatalyst.shipping.model;

/**
 * `#/$defs/Link` — a single HATEOAS link (RFC 8288-style relation):
 * `{href, method, title}`. `method` always set explicitly here even though
 * the schema defaults it to `GET` — an explicit value keeps a client from
 * having to know the schema's default to drive a state transition.
 */
public record Link(String href, String method, String title) {
}
