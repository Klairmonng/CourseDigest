# ADR-001: Course data from `__NEXT_DATA__` through a logged-in Playwright profile

**Status:** Accepted (login step superseded by ADR-004) · **Date:** 2026-10-16 · **Feature:** coursedigest-v1 · **Author:** 10x-Team (Architect + Staff Engineer)

## Context
Lessons sit behind the user's login on learn.deeplearning.ai. Each lesson page is server-rendered (Next.js) and embeds a tRPC state in `<script id="__NEXT_DATA__">` holding `course.getCourseBySlug` (every lesson: slug, name, type, seconds; `listing` = modules in order) and `course.getLessonVideoSubtitle` (captions with start/end seconds). Ungraded labs open a Jupyter server in an iframe whose URL carries a session token.

## Decision
A Playwright persistent context (`.profile/`) holds the user's own sign-in (`coursedigest login`, the user types the password, never the tool). `fetch` loads each lesson page and parses `__NEXT_DATA__`; for labs it waits for the iframe, then downloads that lab's folder through the Jupyter contents API using the iframe URL. Lesson types `quiz` and `graded_notebook` are skipped by rule.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Click "Show transcript" and scrape the DOM | Works without knowing the data layout | Slow, brittle to UI changes, needs rendering per lesson | `__NEXT_DATA__` holds the same captions with exact timings |
| Claude reads lessons in the desktop browser pane | No scraper code | Not a reusable tool; needs a live Claude session; slow | User asked for a tool for 3-4 paths |
| User pastes transcripts | No automation risk | ~30 pastes per course, no labs | Too manual |

## Consequences
### Positive
- One request per lesson, exact timestamps, lesson types known up front.
### Negative
- Depends on DeepLearning.AI's internal page data shape.
### Risks
- Shape changes: all parsing lives in `fetch.py` with fixture tests; a failure names the missing key.
- Automated access to the user's account: one page at a time with a delay, only content the user can already open.

## Dependencies
Playwright (Chromium). Constrains: fetcher is DeepLearning.AI-specific by design.
