# CTO - coursedigest-v1
- **Problem:** 3-4 learning paths x ~10 h each; the user needs the information, not the hours.
- **Build vs buy:** notebook-style summarizers work on pasted text but do not fetch behind the login, run the labs, or produce lesson-level diagrams and watch-moments. Build.
- **Verdict:** a reusable CLI; one live run on `agentic-ai` proves it; the next paths reuse it unchanged.
- **Cost guardrail:** ~$4-6 per course on Opus 5.5 (user approved). Cache by input hash so re-runs are free.
