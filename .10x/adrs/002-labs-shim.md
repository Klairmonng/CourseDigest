# ADR-002: Run labs unmodified with a kernel-startup shim that routes model calls to Claude

**Status:** Accepted (target model superseded by ADR-005) · **Date:** 2026-10-16 · **Feature:** coursedigest-v1 · **Author:** 10x-Team (Architect + Staff Engineer)

## Context
The user has Anthropic and Tavily keys, not OpenAI. Labs call models three ways: `openai.OpenAI().responses.create` (text + images), `aisuite.Client().chat.completions.create(model="openai:...")`, and `anthropic.Anthropic().messages.create(temperature=0)` - and `temperature` is rejected by `claude-opus-5-5`. The labs must run end to end and be shown visually.

## Decision
Execute each notebook with `jupyter nbconvert --execute --allow-errors` from a separate `labs/.venv`, with `IPYTHONDIR` pointing at a profile whose startup file imports `coursedigest.shim`. The shim patches, at kernel start: OpenAI Responses and Chat Completions (translated to Anthropic Messages), aisuite (model string rewritten to `anthropic:` and sampling params dropped), and Anthropic Messages (model forced to the configured one, sampling params dropped). Every call is appended to `trace.jsonl` (inputs with images saved as files, output, tool calls, usage, latency). A dummy `OPENAI_API_KEY` lets lab imports construct clients; no request ever reaches OpenAI.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Edit each notebook to use Claude | Explicit | Per-lab manual work, diverges from the course | Not reusable across courses |
| Only rewrite aisuite model strings | Tiny | Misses direct OpenAI/Anthropic calls and `temperature` | Labs would fail |
| Ask the user for an OpenAI key | Runs as written | User chose Anthropic | Declined |

## Consequences
### Positive
- Notebooks stay byte-identical to the course; the trace gives the visual walkthrough real data.
### Negative
- The translation covers what labs use (text, images, function tools); exotic OpenAI features raise a clear error in the trace.
### Risks
- Lab code is course code run locally: separate venv, run only ungraded labs from the user's own course.

## Dependencies
`labs/.venv` with the course's lab requirements + ipykernel + nbconvert; `coursedigest/shim.py` must import without the tool's other dependencies.
