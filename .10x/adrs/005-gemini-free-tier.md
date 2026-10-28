# ADR-005: Run every model call on Gemini's free tier through its OpenAI-compatible endpoint

**Status:** Accepted (supersedes the model choice in the spec and ADR-002) · **Date:** 2026-10-16 · **Feature:** coursedigest-v1 · **Author:** 10x-Team (CTO + Architect)

## Context
The user will not pay for API usage. Their Anthropic key has no credits. OpenAI's API also needs prepaid credits; Gemini's API (Google AI Studio key) has a free tier with per-minute and per-day request limits. The labs are written against the OpenAI SDK (directly and through aisuite).

## Decision
- One SDK, the OpenAI Python SDK, for the tool and the labs. Default provider: Gemini at `https://generativelanguage.googleapis.com/v1beta/openai/` with `GEMINI_API_KEY`; `LLM_PROVIDER=openai` switches to OpenAI.
- Tool calls (`llm.py`): `chat.completions.parse` with the pydantic models; models `gemini-flash-latest` then `gemini-flash-lite-latest`; per-minute limits are waited out, a spent daily quota moves to the next model, and when every model is spent the run stops with finished items cached.
- Labs (`labs.py` + `shim.py`): the kernel gets `OPENAI_BASE_URL` and `OPENAI_API_KEY` for the provider, so every OpenAI client the lab builds talks to Gemini. The shim rewrites model names, runs Responses calls and direct Anthropic calls as Chat Completions, sends aisuite's other providers through its OpenAI provider, and keeps recording traces.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Keep Claude (ADR-002) | Best quality | Needs paid credits | User declined |
| OpenAI API | Labs run as written | Needs paid credits | Not free |
| Google `google-genai` SDK | Native features | Second SDK; labs still need OpenAI-shaped calls | One SDK covers both |
| Groq free tier | Fast, OpenAI-compatible | Weaker vision and structured output | Gemini covers images and schemas |

## Consequences
### Positive
- $0 per course; labs need fewer translations (only Responses and Anthropic calls).
### Negative
- Free-tier daily quotas can split a course over more than one day.
- Lower model quality than Opus for long synthesis.
### Risks
- Free-tier prompts may be used by Google to improve its products: course transcripts and lab code are sent to Google.
- The `-latest` aliases move to new models; pin `LLM_MODEL` if output changes unexpectedly.
