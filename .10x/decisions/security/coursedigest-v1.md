# Security - coursedigest-v1
- **Threat model:** a malicious or odd transcript/notebook text trying to steer the model (prompt injection) or break the page (HTML/JS injection); leaked secrets; running untrusted code.
- **Controls:** tagged untrusted input + schema-validated output + no model tools; forced autoescape + `textContent` + asset path allowlist on the page; gitignored secrets and session; path checks and graded-material refusal on download; separate venv for lab code.
- **Accepted risks:** lab notebooks execute locally (course code, user's own account); Gemini free tier may use prompts for product improvement.
- Full review: `.10x/reviews/2026-10-16-security-review.md`.
