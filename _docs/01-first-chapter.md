---
title: "Your first chapter"
order: 1
part: "Getting started"
description: "A template chapter showing the house conventions."
duration: 15 minutes
---

This is a template chapter. The big number, breadcrumb, and prev/next pager are
all derived from `order` and the `part`/`part_name` match — add a chapter and it
slots in automatically.

Write in prose with the depth the house style expects: explain the *why*, not just
the *what*. Inline code like `cargo build` stays on one line; long commands in a
table cell wrap because of the `table-layout: fixed` rule in `site.css`.

<div class="callout callout--warn">
  <p class="callout__title">Heads up</p>
  <p>Author callouts as raw HTML — variants: <code>--safe</code>, <code>--warn</code>, <code>--danger</code>.</p>
</div>

To embed a diagram, generate a paired <code>name.svg</code> + <code>name.excalidraw</code>
into <code>assets/diagrams/</code> (see <code>scripts/generate_diagram.py</code>) and include it.
Wrap any literal Liquid braces in a raw block so Jekyll doesn't interpret them:

{% raw %}
```liquid
{% include excalidraw.html
   file="my-diagram"
   alt="A thorough description of the diagram for accessibility."
   caption="Figure 1.1 — what the diagram shows" %}
```
{% endraw %}
