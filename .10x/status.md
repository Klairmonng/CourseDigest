# Status - coursedigest-v1
**Phase:** Implementation (Phase 4) - code complete, 30 tests passing; live run blocked on the user

- [x] Phase 0 Brainstorming - spec `.10x/specs/2026-10-16-coursedigest-design.md`
- [x] Phase 1 Strategy - cto, product-manager
- [x] Phase 2 Design - ADR-001..003, architect, staff-engineer
- [x] Phase 3 Planning - engineering-manager (9 tasks), senior-engineer
- [ ] Phase 4 Implementation - tasks 1-7 done; task 8 (live run) blocked
- [ ] Phase 5 Verification
- [ ] Phase 6 Delivery

## Verified live (2026-10-16)
- Lab venv builds from the course requirements (Python 3.11).
- Both Module 2 labs execute end to end under nbconvert; the shim routed `openai.responses` (gpt-4o-mini) and aisuite `openai.chat` (gpt-4.1) to `claude-opus-5-5` and wrote traces.

## Blockers (user)
1. **Login:** run `.\.venv\Scripts\coursedigest login` in your own PowerShell (visible browsers cannot start from the agent here).
2. **Anthropic API credits:** the key in `.env` is valid but the account balance is too low (HTTP 400). Add credits at console.anthropic.com -> Plans & Billing (~$10 covers one course with labs).
