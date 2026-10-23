# Shared deck scaffold: API Patterns & Practices: REST

One Red Hat house-style scaffold, reused by all three decks in this series:

| Deck dir | What it is |
|---|---|
| `../api-patterns-rest-100/` | 100-level **concepts**: the what & why of REST, stack-agnostic |
| `../api-patterns-rest-quarkus/` | **Quarkus** implementation of the same patterns |
| `../api-patterns-rest-python/` | **Python / FastAPI** implementation of the same patterns |

## What lives here

- `deck-helpers.js`: the bundled Red Hat deck helper library (COLOR / FONT / W / H
  + `addContentTitle` / `addBullets` / `addTwoColBullets` / `addStatusTable` /
  `addCodeSlide` / `addDiagramSlide` / `addSectionDivider` / `addFooter` / `addNotes`).
  **Do not rewrite**: extend only.
- `dgen.py`: the Scene diagram engine (SVG + Excalidraw emitters).
- `build_diagrams.py`: batch builder; renders each scene SVG → PNG via `cairosvg`
  (the skill's bundled `soffice.py` converter is absent in this environment).
- `diagrams.py`: the **nine concept diagrams** every deck can embed:
  `r02-decision-axes`, `r03-resource-model`, `r05-idempotency-matrix`,
  `r08-pagination`, `r10-async-flow`, `r12-hateoas-fsm`, `r15-range`,
  `r21-multiprotocol`, `r25-deployment-tiers`.
- `assets/`: brand assets (cover panel, section panel, logos).
- `png/`: rendered concept-diagram PNGs (what `addDiagramSlide` reads).
- `diagrams/`: the matching `.svg` + `.excalidraw` sources.
- `node_modules/`: `pptxgenjs` (shared across decks).

## Rebuild the concept diagrams

```bash
cd presentation/_shared
python3 build_diagrams.py        # -> diagrams/*.svg + *.excalidraw, png/*.png
```

## How each deck reuses this

A deck's `deck.js` points the helper's asset/PNG paths at `_shared/` before
requiring it, then requires the shared helpers:

```js
const path = require("path");
const SHARED = path.resolve(__dirname, "../_shared");
process.env.DECK_ASSETS = `${SHARED}/assets`;
process.env.DECK_PNG   = `${SHARED}/png`;
const H = require(`${SHARED}/deck-helpers.js`);
```

Run a deck with the shared `pptxgenjs` on the module path:

```bash
cd presentation/api-patterns-rest-100     # or -quarkus / -python
export NODE_PATH="$(cd ../_shared/node_modules && pwd)"
node deck.js
```

To add the next implementation deck, copy an existing deck dir, keep the
`_shared` wiring above, and swap the slide content.
