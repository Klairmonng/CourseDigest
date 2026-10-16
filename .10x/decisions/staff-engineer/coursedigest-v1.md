# Staff Engineer - coursedigest-v1
- **Standards:** Python 3.11, pydantic v2 models as the only data contracts, JSON written with `indent=2, ensure_ascii=False`, UTF-8 everywhere (Windows).
- **Cross-cutting:** logging to stderr; secrets only from `.env` via python-dotenv; the lab token and API keys are never logged or written to traces.
- **Testing:** pytest, synthetic fixtures only (no course text in the repo), fake Claude client.
- **Reuse:** one structured-call helper and one cache-key function for every Claude call.
- **Hygiene:** no unused modules or options; dependencies declared in `pyproject.toml`.
