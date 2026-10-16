# CourseDigest v1 - Design

**Date:** 2026-10-16 · **Status:** Approved by user · **Feature slug:** `coursedigest-v1`

## Problem
The user must get through 3-4 DeepLearning.AI learning paths of ~10 hours each. They need the information, not the hours: what each lesson teaches in plain English, a worked example, a diagram, which video moments are worth watching, and the ungraded labs run end to end with a visual explanation of how they work. They already write their own portfolio; the tool only supplies the content.

## Scope
**In:** any `learn.deeplearning.ai/courses/<slug>` course the user can open; video and reading lessons; ungraded labs (`notebook`, `paid_notebook`); a static visual site per course.
**Out:** quizzes and graded labs (never fetched, run or stored); other platforms; portfolio writing; a hosted service.

## Commands (`coursedigest`, Python 3.11)
| Command | Does |
|---|---|
| `login` | Opens Chromium as a normal (non-automated) window on `.profile/`; the user signs in; closing the window ends it (ADR-004). |
| `fetch <course-url-or-slug>` | Reads the course map and every lesson from the page's server-rendered `__NEXT_DATA__` (captions with timestamps, reading text); downloads each ungraded lab's folder from its Jupyter server. Resumable; `--force` refetches. |
| `digest <course>` | One model call per video/reading lesson -> `LessonDigest`; one synthesis call -> `CourseSummary`; writes `digests/<course>.json`. Cached by input hash. |
| `labs <course>` | Runs each lab notebook unmodified in `labs/.venv` with the shim loaded at kernel start; records `trace.jsonl`; extracts output images; one model call per lab -> `LabWalkthrough`. |
| `site <course>` | Renders `site/<course>/index.html` (+ `assets/`). |
| `all <course-url>` | fetch -> digest -> labs -> site. |

## Data contracts (`coursedigest/models.py`)
- `cache/<course>/course.json` - `CourseMap {slug, name, total_seconds, modules[{label, name, lessons[slug]}], lessons{slug: LessonMeta{index, slug, name, type, seconds, module}}}`
- `cache/<course>/lessons/<NN>-<slug>.json` - `LessonContent {meta, url, captions[{start, end, text}] | None, reading | None}`
- `labs/<course>/<NN>-<folder>/` - the lab's files + `lab.json {meta, notebook, source_dir}`; after a run: `<nb>.executed.ipynb`, `trace.jsonl`, `outputs/*.png`, `walkthrough.json`
- `digests/<course>.json` - `CourseDigest {course: CourseSummary, lessons[LessonDigest], model, prompt_version, generated_at}`

`LessonDigest`: `slug, title, module, kind, minutes, importance (must|good|skip), importance_reason, tldr, summary, key_ideas[{idea, detail}], example{title, scenario, steps[], takeaway}, diagram, watch[{start, end, why}], terms[{term, definition}], flashcards[{q, a}]`.
`Diagram`: `kind (flow|cycle|hub|compare|layers), title, nodes[{id, label, note, group}], edges[{source, target, label}]`.
`CourseSummary`: `big_picture, top_takeaways[], concept_map (Diagram), module_overviews[{module, one_liner}]`.
`LabWalkthrough`: `slug, title, module, goal, pattern, diagram, steps[{title, what_happens, code_ref, call_refs[], image}], results, try_next[], run{status, cells, errors, calls, input_tokens, output_tokens, seconds}`.

## Architecture
Flat package, one module per stage, pure functions where possible, I/O at the edges:
`fetch.py` (Playwright) -> `cache/` -> `digest.py` -> `digests/` ; `labs.py` (venv + nbconvert, `shim.py` in the kernel) -> `labs/` ; `site.py` (Jinja2 + own SVG diagram renderer) -> `site/`. Every model call from the tool goes through `llm.py` (structured-call helper + cache key).

## Key decisions (ADRs)
- ADR-001 Course data from `__NEXT_DATA__` through a logged-in Playwright profile.
- ADR-002 Labs run unmodified; a kernel-startup shim routes OpenAI Responses, OpenAI Chat, aisuite and Anthropic calls and records traces (target model: ADR-005).
- ADR-004 Sign-in happens in a normal browser window; automation only reuses the saved session.
- ADR-005 Models run on Gemini's free tier through its OpenAI-compatible endpoint; OpenAI optional.
- ADR-003 Static site with a small in-house SVG renderer for five diagram kinds; no CDN at view time.

## Model usage (ADR-005)
OpenAI SDK against Gemini's OpenAI-compatible endpoint (`GEMINI_API_KEY`, free tier): `gemini-flash-latest`, falling back to `gemini-flash-lite-latest` when its daily quota is spent; per-minute limits are waited out. Structured output via `client.chat.completions.parse` with the pydantic models. `LLM_PROVIDER=openai` switches to OpenAI (paid). Transcripts are wrapped as data inside tags; the model gets no tools. Cache key = sha256(model, prompt_version, input) so re-runs and next-day resumes are free.

## Error handling
- Not logged in / session expired -> stop with "run `coursedigest login`".
- Lesson without captions -> stored with `captions: null`, digest marks it "no transcript".
- Lab server slow to start -> wait up to 120 s for the iframe, then skip the lab with a reason.
- Refusal / invalid output -> the lesson is recorded as failed and the run continues; a spent daily quota on every model stops the run (finished lessons stay cached).
- Lab cell errors -> notebook executes with `--allow-errors`; errors counted and shown in the walkthrough.

## Testing
Pytest with synthetic fixtures (no course content): `__NEXT_DATA__` parsing, lesson classification, cache keys, model validation, shim translation functions, diagram renderer, site build. The model is replaced by a fake in tests. One live end-to-end run on `agentic-ai`.

## Cost
$0 on Gemini's free tier. Limits: daily request quotas per model; a course may need more than one day if a quota runs out. Free-tier prompts may be used by Google to improve its products.
