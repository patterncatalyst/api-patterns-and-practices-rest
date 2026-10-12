package com.patterncatalyst.shipping;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.util.ArrayList;
import java.util.List;

/**
 * RFC 6902 JSON Patch, hand-rolled against Jackson's JsonNode tree so this
 * chapter needs no extra dependency (the same choice {@code
 * BookingResource#applyMergePatch} makes for RFC 7396 JSON Merge Patch).
 *
 * <p>{@link #apply} never mutates its {@code target} argument — every
 * structural operation (add/remove/replace/move/copy) works against a deep
 * copy and returns a brand-new tree, so a caller can always fall back to
 * the original document if a later operation in the same patch document
 * fails partway through.
 *
 * <p>Supports all six RFC 6902 §4 operations: add, remove, replace, move,
 * copy, test. JSON Pointer (RFC 6901) path syntax is implemented directly,
 * including the {@code ~1}/{@code ~0} escapes and the {@code -} "append"
 * array index.
 */
public final class JsonPatch {

    private JsonPatch() {
    }

    /** A patch op addressed a path that doesn't exist, or the document is malformed. */
    public static class JsonPatchException extends RuntimeException {
        public JsonPatchException(String message) {
            super(message);
        }
    }

    /** A {@code test} operation's actual value did not match its expected {@code value} (RFC 6902 §4.6). */
    public static class TestFailedException extends RuntimeException {
        public TestFailedException(String message) {
            super(message);
        }
    }

    public static JsonNode apply(JsonNode target, JsonNode patchOps) {
        if (patchOps == null || !patchOps.isArray()) {
            throw new JsonPatchException("a JSON Patch document must be a JSON array of operations");
        }
        JsonNode doc = target;
        for (JsonNode opNode : patchOps) {
            if (!opNode.isObject() || !opNode.has("op") || !opNode.has("path")) {
                throw new JsonPatchException("each operation needs an 'op' and a 'path'");
            }
            String op = opNode.get("op").asText();
            List<String> tokens = tokenize(opNode.get("path").asText());
            switch (op) {
                case "add" -> doc = add(doc, tokens, requireValue(opNode));
                case "remove" -> doc = remove(doc, tokens);
                case "replace" -> doc = replace(doc, tokens, requireValue(opNode));
                case "move" -> {
                    List<String> from = tokenize(requireText(opNode, "from"));
                    JsonNode value = get(doc, from);
                    doc = add(remove(doc, from), tokens, value);
                }
                case "copy" -> {
                    List<String> from = tokenize(requireText(opNode, "from"));
                    doc = add(doc, tokens, get(doc, from).deepCopy());
                }
                case "test" -> {
                    JsonNode actual = get(doc, tokens);
                    JsonNode expected = opNode.has("value") ? opNode.get("value") : NullNode.getInstance();
                    if (!actual.equals(expected)) {
                        throw new TestFailedException("test failed at '" + opNode.get("path").asText()
                                + "': expected " + expected + ", got " + actual);
                    }
                }
                default -> throw new JsonPatchException("unsupported op: " + op);
            }
        }
        return doc;
    }

    // ------------------------------------------------------------------
    // RFC 6901 JSON Pointer
    // ------------------------------------------------------------------

    private static List<String> tokenize(String pointer) {
        if (pointer.isEmpty()) {
            return List.of();
        }
        if (!pointer.startsWith("/")) {
            throw new JsonPatchException("invalid JSON Pointer: '" + pointer + "'");
        }
        String[] raw = pointer.substring(1).split("/", -1);
        List<String> tokens = new ArrayList<>(raw.length);
        for (String t : raw) {
            tokens.add(t.replace("~1", "/").replace("~0", "~"));
        }
        return tokens;
    }

    private static String requireText(JsonNode opNode, String field) {
        JsonNode v = opNode.get(field);
        if (v == null || !v.isTextual()) {
            throw new JsonPatchException("'" + opNode.get("op").asText() + "' requires a '" + field + "' string");
        }
        return v.asText();
    }

    private static JsonNode requireValue(JsonNode opNode) {
        if (!opNode.has("value")) {
            throw new JsonPatchException("'" + opNode.get("op").asText() + "' requires a 'value'");
        }
        return opNode.get("value");
    }

    /** Index for a READ (get/remove/replace-target): "-" is not a readable index. */
    private static int readIndex(String token, int size) {
        if ("-".equals(token)) {
            throw new JsonPatchException("'-' is only valid as an add/move/copy destination, not a read");
        }
        return parseIndex(token, size, size - 1);
    }

    /** Index for a WRITE destination (add/move/copy target): "-" means append. */
    private static int writeIndex(String token, int size) {
        if ("-".equals(token)) {
            return size;
        }
        return parseIndex(token, size, size);
    }

    private static int parseIndex(String token, int size, int max) {
        int idx;
        try {
            idx = Integer.parseInt(token);
        } catch (NumberFormatException e) {
            throw new JsonPatchException("invalid array index: '" + token + "'");
        }
        if (idx < 0 || idx > max) {
            throw new JsonPatchException("array index out of bounds: " + idx + " (size " + size + ")");
        }
        return idx;
    }

    private static JsonNode get(JsonNode doc, List<String> tokens) {
        JsonNode node = doc;
        for (String token : tokens) {
            if (node.isArray()) {
                node = node.get(readIndex(token, node.size()));
            } else if (node.isObject()) {
                if (!node.has(token)) {
                    throw new JsonPatchException("path segment not found: '" + token + "'");
                }
                node = node.get(token);
            } else {
                throw new JsonPatchException("cannot descend into a scalar at '" + token + "'");
            }
        }
        return node;
    }

    /** Navigates to the container (object/array) that directly holds the path's last token. */
    private static JsonNode navigateToParent(JsonNode doc, List<String> tokens) {
        JsonNode node = doc;
        for (int i = 0; i < tokens.size() - 1; i++) {
            String token = tokens.get(i);
            if (node.isArray()) {
                node = node.get(readIndex(token, node.size()));
            } else if (node.isObject()) {
                if (!node.has(token)) {
                    throw new JsonPatchException("path segment not found: '" + token + "'");
                }
                node = node.get(token);
            } else {
                throw new JsonPatchException("cannot descend into a scalar at '" + token + "'");
            }
        }
        return node;
    }

    private static JsonNode add(JsonNode target, List<String> tokens, JsonNode value) {
        if (tokens.isEmpty()) {
            return value;
        }
        JsonNode doc = target.deepCopy();
        JsonNode parent = navigateToParent(doc, tokens);
        String last = tokens.get(tokens.size() - 1);
        if (parent.isArray()) {
            ((ArrayNode) parent).insert(writeIndex(last, parent.size()), value);
        } else if (parent.isObject()) {
            ((ObjectNode) parent).set(last, value);
        } else {
            throw new JsonPatchException("cannot add into a scalar");
        }
        return doc;
    }

    private static JsonNode replace(JsonNode target, List<String> tokens, JsonNode value) {
        if (tokens.isEmpty()) {
            return value;
        }
        JsonNode doc = target.deepCopy();
        JsonNode parent = navigateToParent(doc, tokens);
        String last = tokens.get(tokens.size() - 1);
        if (parent.isArray()) {
            ((ArrayNode) parent).set(readIndex(last, parent.size()), value);
        } else if (parent.isObject()) {
            if (!parent.has(last)) {
                throw new JsonPatchException("path segment not found: '" + last + "'");
            }
            ((ObjectNode) parent).set(last, value);
        } else {
            throw new JsonPatchException("cannot replace into a scalar");
        }
        return doc;
    }

    private static JsonNode remove(JsonNode target, List<String> tokens) {
        if (tokens.isEmpty()) {
            throw new JsonPatchException("cannot remove the document root");
        }
        JsonNode doc = target.deepCopy();
        JsonNode parent = navigateToParent(doc, tokens);
        String last = tokens.get(tokens.size() - 1);
        if (parent.isArray()) {
            ((ArrayNode) parent).remove(readIndex(last, parent.size()));
        } else if (parent.isObject()) {
            if (!parent.has(last)) {
                throw new JsonPatchException("path segment not found: '" + last + "'");
            }
            ((ObjectNode) parent).remove(last);
        } else {
            throw new JsonPatchException("cannot remove from a scalar");
        }
        return doc;
    }
}
