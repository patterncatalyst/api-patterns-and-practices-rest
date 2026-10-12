#!/usr/bin/env python3
"""Fig 14 — Ch14: the four versioning strategies — URI, query parameter,
custom header, and media type — compared by where the version lives and
what it costs intermediate caches; plus a v1-vs-v2 shape diff for the same
resource."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 970, 740

COL_STRATEGY = {"x": 30, "w": 150}
COL_REQUEST = {"x": 190, "w": 330}
COL_LOCATION = {"x": 530, "w": 200}
COL_CACHE = {"x": 740, "w": 200}
HEADER_Y, HEADER_H = 30, 50
ROW_H = 90
ROW_GAP = 8
FIRST_ROW_Y = 100

ROWS = [
    ("URI path", ["GET /v1/bookings/42"],
     "version segment in the path",
     "cache key includes the path — works with standard HTTP caches as-is"),
    ("Query parameter", ["GET /bookings/42?version=1"],
     "version in the query string",
     "caches must vary on the query string; some CDNs strip unknown params"),
    ("Custom header", ["GET /bookings/42", "X-API-Version: 1"],
     "version in a request header",
     "needs Vary: X-API-Version or a cache serves the wrong version next"),
    ("Media type", ["GET /bookings/42", "Accept: application/vnd.shipping.v1+json"],
     "version in the negotiated media type",
     "needs Vary: Accept; version and representation negotiated together"),
]

nodes = [
    {"x": COL_STRATEGY["x"], "y": HEADER_Y, "w": COL_STRATEGY["w"], "h": HEADER_H,
     "lines": ["Strategy"], "style": "ink"},
    {"x": COL_REQUEST["x"], "y": HEADER_Y, "w": COL_REQUEST["w"], "h": HEADER_H,
     "lines": ["Request shape"], "style": "ink"},
    {"x": COL_LOCATION["x"], "y": HEADER_Y, "w": COL_LOCATION["w"], "h": HEADER_H,
     "lines": ["Where it lives"], "style": "ink"},
    {"x": COL_CACHE["x"], "y": HEADER_Y, "w": COL_CACHE["w"], "h": HEADER_H,
     "lines": ["Caching implication"], "style": "ink"},
]

for i, (name, req_lines, location, cache) in enumerate(ROWS):
    y = FIRST_ROW_Y + i * (ROW_H + ROW_GAP)
    nodes.append({"x": COL_STRATEGY["x"], "y": y, "w": COL_STRATEGY["w"], "h": ROW_H,
                  "lines": [name], "style": "box"})
    nodes.append({"x": COL_REQUEST["x"], "y": y, "w": COL_REQUEST["w"], "h": ROW_H,
                  "lines": req_lines, "style": "sub"})
    nodes.append({"x": COL_LOCATION["x"], "y": y, "w": COL_LOCATION["w"], "h": ROW_H,
                  "lines": [location], "style": "box"})
    nodes.append({"x": COL_CACHE["x"], "y": y, "w": COL_CACHE["w"], "h": ROW_H,
                  "lines": [cache], "style": "box"})

TABLE_BOTTOM = FIRST_ROW_Y + len(ROWS) * (ROW_H + ROW_GAP)

nodes += [
    {"x": 140, "y": TABLE_BOTTOM + 30, "w": 330, "h": 130,
     "lines": ["v1 response body", "{", "  \"price\": 420.00,",
               "  \"cargoDescription\": \"20ft reefer, frozen goods\"", "}"], "style": "sub"},
    {"x": 500, "y": TABLE_BOTTOM + 30, "w": 330, "h": 130,
     "lines": ["v2 response body", "{", "  \"quote\": {\"amount\":420.00,\"currency\":\"USD\"},",
               "  \"cargo\": [{\"description\":\"20ft reefer, frozen goods\"}]", "}"], "style": "sub"},
]

edges = [
    {"x1": 470, "y1": TABLE_BOTTOM + 95, "x2": 500, "y2": TABLE_BOTTOM + 95,
     "label": "breaking shape change", "amber": True, "dashed": True},
]

notes = [
    {"x": 485, "y": TABLE_BOTTOM + 210, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
     "text": "Query-param and header/media-type strategies need Vary or an intermediate cache serves the wrong version to the next client — URI versioning avoids this because the version is already part of the cache key."},
]

generate_diagram.emit("14-versioning-strategies", W, H, nodes=nodes, edges=edges, notes=notes)
