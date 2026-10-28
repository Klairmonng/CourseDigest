# CTO - coursedigest-v1
- **Problem:** 3-4 learning paths x ~10 h each; the user needs the information, not the hours.
- **Build vs buy:** notebook-style summarizers work on pasted text but do not fetch behind the login, run the labs, or produce lesson-level diagrams and watch-moments. Build.
- **Verdict:** a reusable CLI; one live run on `agentic-ai` proves it; the next paths reuse it unchanged.
- **Cost guardrail:** $0 - the user does not pay for API usage; Gemini free tier (ADR-005). Cache by input hash so re-runs and next-day resumes are free.
