# Architect - coursedigest-v1
## Components
| Module | Responsibility | Depends on |
|---|---|---|
| `models.py` | pydantic contracts (spec) | pydantic |
| `fetch.py` | login, course map, lesson content, lab download | Playwright, models |
| `llm.py` | the one structured-call helper + cache key + quota handling | openai (Gemini endpoint) |
| `digest.py` | lesson + synthesis prompts, cache, `digests/<course>.json` | llm, models |
| `labs.py` | lab venv, execution, image extraction, walkthrough | subprocess, nbformat, llm |
| `shim.py` | in-kernel model routing + trace | openai (+ anthropic, aisuite when installed; runs in the labs venv) |
| `site.py` + `templates/site.html.j2` | diagrams to SVG, page render | jinja2, models |
| `cli.py` | argparse wiring | all |

## Boundaries
- Only `fetch.py` knows DeepLearning.AI. Only `shim.py` runs inside lab kernels.
- Every model call from the tool goes through `llm.py` (ADR-005).

## Failure modes
Session expired, page data shape change, lab server timeout, model refusal, invalid output or spent free-tier quota, lab cell errors: each is recorded per item and the run continues (see spec).
