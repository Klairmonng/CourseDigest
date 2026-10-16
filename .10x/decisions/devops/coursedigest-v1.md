# DevOps - coursedigest-v1
- **Ship:** PR `feature/coursedigest-v1` -> `dev`; the user merges; `dev` -> `main` when they choose.
- **Install:** README setup (Python 3.11 venv, `pip install -e .[dev]`, `playwright install chromium`, `.env` from `.env.example`). The labs venv builds itself on the first `labs` run.
- **CI:** none yet (personal tool). `pytest -q` before every PR.
- **Rollback:** `git revert`; generated outputs are reproducible from the cache.
