# DBA - coursedigest-v1
- **Storage:** JSON files validated by pydantic on every read; no database, no migrations.
- **Keys:** lessons by `<index>-<slug>`, labs by `<index>-<folder>`, model answers by `cache_key(model, prompt_version, prompt)` under `cache/<course>/llm/`.
- **Schema changes:** bump `PROMPT_VERSION` (digest.py / labs.py) when an output model or prompt changes, so stale cached answers are not reused.
- **Volume:** ~50 lesson files + ~30 cached answers per course; a few MB. No indexing needed.
