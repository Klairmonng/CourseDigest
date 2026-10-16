# SDE - coursedigest-v1

## Built
| File | What |
|---|---|
| `coursedigest/models.py` | pydantic contracts from the spec |
| `coursedigest/fetch.py` | `login`, `fetch_course`: course map + captions + readings from `__NEXT_DATA__` via `context.request` (no rendering); labs via a rendered page, iframe src -> Jupyter contents API; requirements block lifted from the setup reading |
| `coursedigest/claude.py` | `Claude.structured`: `beta.messages.parse` + `output_format`, adaptive thinking, effort, `fallbacks="default"`, cache by key, usage + cost |
| `coursedigest/digest.py` | lesson + course prompts, 4 workers, watch moments clamped to caption range |
| `coursedigest/shim.py` | OpenAI Chat/Responses -> Anthropic translation, Anthropic param cleanup, original-block replay for tool loops, trace + image assets |
| `coursedigest/labs.py` | `labs/.venv` with a sys-prefix kernel, IPYTHONDIR startup file, nbconvert `--allow-errors`, image extraction (png and inline HTML), walkthrough prompt |
| `coursedigest/site.py` + `templates/site.html.j2` | five SVG layouts, glossary, flashcards, lab steps with call references and trace viewer |
| `coursedigest/cli.py` | `login`, `fetch`, `digest`, `labs`, `site`, `all`; clean errors for FetchError/ClaudeError |
| `tests/` | 30 tests, synthetic fixtures |

## Deviations from plan
- Added `claude.py` (one helper for digest and labs) - reflected in the spec and architect file.
- Lesson URLs need the title suffix (`title_slug`, mirrors encodeURIComponent); `/courses/<slug>` redirects to lesson 1 with the full course data.
- Visible browser windows cannot start from the agent's process tree on this machine (`spawn UNKNOWN` for chrome.exe and msedge.exe, sandbox on or off); headless works. `login` is run by the user in their own PowerShell.
- Two bugs caught by tests: `is_graded` matched "ungraded" (would have skipped every lab); Jinja autoescape was off for `.j2` (model text rendered as HTML) - both fixed.

## Tech debt
- Fetcher is DeepLearning.AI-specific by design (ADR-001).
- Shim covers text, images and function tools; streaming and other OpenAI tool types raise a clear NotImplementedError into the trace.
