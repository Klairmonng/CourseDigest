# EM - coursedigest-v1
| # | Task | Est. | Depends |
|---|---|---|---|
| 1 | pyproject, models.py, tests skeleton | 0.5 h | - |
| 2 | fetch.py: login, course map, captions, readings + tests | 1.5 h | 1 |
| 3 | fetch.py: lab download | 1 h | 2 |
| 4 | claude.py + digest.py: helper, cache, lesson + synthesis prompts + tests | 1.5 h | 1 |
| 5 | site.py: SVG renderer + template + tests | 2 h | 1 |
| 6 | shim.py + tests | 1.5 h | - |
| 7 | labs.py: venv, execute, images, walkthrough | 1.5 h | 4, 6 |
| 8 | cli.py + live run on agentic-ai | 1.5 h | all |
| 9 | QA + security review, PR to dev | 1 h | 8 |

Risks first: 2 and 6 (external shapes). The live run needs the user's `.env` keys before 4 and 7 run for real.
