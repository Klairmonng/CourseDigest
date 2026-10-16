# Handoff -> SDE (live run) then QA + Security
Code for tasks 1-7 is in `coursedigest/` (see `decisions/sde/coursedigest-v1.md`); 30 tests pass.

## To finish task 8 once the user has logged in and added API credits
1. `coursedigest fetch agentic-ai` - expect ~37 lesson files in `cache/agentic-ai/lessons/` and 8 lab folders in `labs/agentic-ai/` (two Module 2 labs were staged from the user's zip; fetch skips folders that already have `lab.json`).
2. `coursedigest digest agentic-ai` - check failed lessons and the printed cost.
3. `coursedigest labs agentic-ai` - check each lab's cell errors and trace; fix shim gaps per lab.
4. `coursedigest site agentic-ai` - open `site/agentic-ai/index.html`, check diagrams, lab steps, trace viewer, phone width.

## Then QA + Security (Phase 5)
- QA: live-run results per lab, diagram readability, site on mobile width, re-run costs $0 (cache).
- Security: `.profile` and `.env` gitignored; lab token never logged; transcripts and lab text treated as data in prompts; site escapes all model text (tested) and trace images only load from `assets/`.

Course data shape: `props.pageProps.trpcState.json.queries[]` keyed by `["course","getCourseBySlug"]`, `["course","getLessonVideoSubtitle"]`, `["course","getReadingMaterial"]`, `["user","getUserProfile"]`.
