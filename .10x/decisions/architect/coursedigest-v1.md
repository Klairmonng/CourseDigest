# Architect - coursedigest-v1
## Components
| Module | Responsibility | Depends on |
|---|---|---|
| `models.py` | pydantic contracts (spec) | pydantic |
| `fetch.py` | login, course map, lesson content, lab download | Playwright, models |
| `claude.py` | the one structured-call helper + cache key | anthropic |
| `digest.py` | lesson + synthesis prompts, cache, `digests/<course>.json` | claude, models |
| `labs.py` | lab venv, execution, image extraction, walkthrough | subprocess, nbformat, claude |
| `shim.py` | in-kernel routing to Claude + trace | anthropic only (runs in the labs venv) |
| `site.py` + `templates/site.html.j2` | diagrams to SVG, page render | jinja2, models |
| `cli.py` | argparse wiring | all |

## Boundaries
- Only `fetch.py` knows DeepLearning.AI. Only `shim.py` runs inside lab kernels.
- Every Claude call goes through `claude.py`.

## Failure modes
Session expired, page data shape change, lab server timeout, Claude refusal or invalid output, lab cell errors: each is recorded per item and the run continues (see spec).
