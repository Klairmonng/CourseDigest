# ADR-004: Sign in through a normal browser window; automate only with the saved session

**Status:** Accepted (supersedes the login step of ADR-001) · **Date:** 2026-10-16 · **Feature:** coursedigest-v1 · **Author:** 10x-Team (Architect + Security)

## Context
The user signs in to DeepLearning.AI with Google. Google refuses sign-in ("This browser or app may not be secure") in a browser driven by automation, which is what ADR-001's Playwright login window was.

## Decision
`coursedigest login` starts Playwright's bundled Chromium as an ordinary process (`--user-data-dir=.profile`, no remote debugging, no automation) and waits until the user closes it. The user signs in by hand. `fetch` then opens the same profile headless and uses only the DeepLearning.AI session; Google is not involved after sign-in.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Hide automation flags from Google in the driven window | One code path | Evades a bot check | Not acceptable |
| User copies the session cookie into a file | Works with any browser | Handling a raw session token by hand; fiddly | Riskier and harder for the user |
| Use the installed Chrome profile | Already signed in | Chrome's app-bound cookie encryption blocks other binaries; Chrome cannot be started from the agent here | Does not work |

## Consequences
### Positive
- Sign-in works with Google, email, or any provider, exactly as in a normal browser.
### Negative
- The login window must be started from the user's own terminal on this machine (visible browsers cannot start from the agent's process tree).
### Risks
- The session cookie lives in `.profile/` (gitignored). When it expires, `fetch` stops with "run `coursedigest login`".
