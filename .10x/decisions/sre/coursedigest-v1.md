# SRE - coursedigest-v1 runbook
| Symptom | Cause | Fix |
|---|---|---|
| `error: not signed in` | Session in `.profile/` expired | Run `coursedigest login` from your own terminal, sign in, close the window |
| `daily free-tier quota used up for every model` | Gemini free daily quotas spent | Run the same command tomorrow; finished lessons and labs are cached |
| Long pauses, "busy" lines | Gemini 503 / per-minute limits | Nothing: the tool waits and switches models |
| A lab shows cell errors | Lab expects a service or feature the free setup lacks | Read the error in the walkthrough; add `coursedigest.json` services/env for that lab, rerun with `labs <course> --only <NN>` |
| `lab ... did not load within 120s` | Pro-only notebook or slow lab server | Expected for Pro-only items; otherwise rerun `fetch` |
| Output looks different after a while | `-latest` model aliases moved | Pin `LLM_MODEL` in `.env` |
