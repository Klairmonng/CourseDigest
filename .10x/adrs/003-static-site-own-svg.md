# ADR-003: Static site with an in-house SVG renderer for five diagram kinds

**Status:** Accepted · **Date:** 2026-10-16 · **Feature:** coursedigest-v1 · **Author:** 10x-Team (Architect + Staff Engineer)

## Context
Visual aids are a core ask. Claude must describe diagrams as data (so they are validated and restyled consistently), and the site must open from disk on any device.

## Decision
Claude returns a `Diagram` (`flow | cycle | hub | compare | layers`, nodes, edges). `site.py` lays each kind out deterministically and emits inline SVG. One self-contained `index.html` per course (data, CSS, JS inline; lab images under `assets/`).

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Mermaid from a CDN | Any graph shape | Needs network at view time, uneven styling, layout surprises | Five kinds cover lesson diagrams |
| Streamlit / local server | Interactive | Needs a running process | A file is simpler to keep and share |
| Claude Artifact app | Hosted | Tied to claude.ai; data size limits | Optional extra, not the core |

## Consequences
### Positive
- Offline, consistent visuals; diagrams testable as pure functions.
### Negative
- Arbitrary graphs are out; Claude is told to pick the closest kind.
### Risks
- Overlapping labels on long text: labels wrap and are capped in length by the schema.
