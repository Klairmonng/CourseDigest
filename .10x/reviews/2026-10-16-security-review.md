# Security review - coursedigest-v1 (2026-10-16)

| Area | Finding | Status |
|---|---|---|
| Secrets | `.env` (GEMINI_API_KEY, TAVILY_API_KEY) and `.profile/` (DeepLearning.AI session) are gitignored; nothing reads or prints key values; the lab Jupyter token stays inside `fetch.py` requests and is never logged. | OK |
| Sign-in | The user types their password in a normal browser window (ADR-004); the tool never handles credentials. | OK |
| Untrusted text -> model | Transcripts, readings and lab notebooks are wrapped in `<lesson>`, `<notes>`, `<lab>` tags and named as material, not instructions; the model has no tools; output must validate against the pydantic schema. | OK |
| Untrusted text -> page | Jinja autoescape is forced on (a test injects `</script>` through a TL;DR); trace JSON escapes `</`; trace text is inserted with `textContent`; trace images load only from `assets/` paths matching `^assets/[\w.\-/]+$`. A real bug (autoescape off for `.j2`) was caught by this test and fixed. | OK |
| Lab files | Paths from the lab server are checked against the lab folder (`safe_relative`); graded folders and files are refused by pattern (`(?<!un)graded|assignment|autograder`). | OK |
| Lab code execution | Course notebooks run locally in a separate venv (`labs/.venv`) under the user's account; only ungraded labs from the user's own course. Accepted risk, documented in ADR-002. | Accepted |
| Data sharing | Gemini free-tier prompts may be used by Google to improve its products: course transcripts and lab code are sent to Google (ADR-005). | Accepted by user (chose free tier) |
| Account | Fetching uses the user's own session, one page at a time with a 1 s pause. | OK |
