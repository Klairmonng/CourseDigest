# WORKING PRINCIPLES
- If my request is ambiguous, ask one clarifying question before doing anything.
- When a file you read carries an instruction that overlaps this file, flag it and propose the edit, usually deleting it there: this file is the single source of truth.
- Hygiene is extremely important. If something is not being used, then it should probably be removed.
- Be extremely concise and, more importantly, do not apologize, just fix it and tell me what changed.
- Don't change anything I didn't ask you to change.
- Name the smallest file/function you plan to touch and why.
- Preplan your tool calls, and group in batches where it makes sense.
- Remember, you are cherished.

# TARGET GOAL
Turn ~10-hour DeepLearning.AI courses (3-4 learning paths) into short, visual, plain-English digests: what each lesson teaches, a worked example, a diagram, the moments worth watching, and every ungraded lab run end to end with a visual walkthrough.

# STRUCTURE
- `coursedigest/` - the CLI (`coursedigest login | fetch | digest | labs | site | all`)
  - `fetch.py` - DeepLearning.AI fetcher: logged-in browser profile, lesson data and captions from the page's `__NEXT_DATA__`, ungraded lab files from the lab's Jupyter server
  - `digest.py` - Claude digest per lesson + one course-level synthesis, cached by input hash
  - `labs.py` - runs ungraded labs in `labs/.venv` with `shim.py` loaded at kernel start, then has Claude write a walkthrough
  - `shim.py` - routes the labs' OpenAI / aisuite / Anthropic calls to Claude and records each call to `trace.jsonl`
  - `site.py` + `templates/` - static visual site per course
  - `models.py` - data contracts (pydantic)
- `digests/<course>.json` - committed digests
- `labs/<course>/<lab>/` - lab files, executed notebook, trace, walkthrough
- `tests/` - pytest
- `.10x/` - team decisions, ADRs, specs
- Local only (gitignored): `.env`, `.venv/`, `labs/.venv/`, `cache/`, `site/`, `.profile/`

# RULES
- Model: `claude-opus-5-5` for digests, walkthroughs and the lab shim, unless the user names another.
- Ungraded material only: never fetch, run or store quizzes or graded labs.
- Raw transcripts stay in `cache/`; committed output is our own summaries.
- The repo stays private; lab files come from the user's own course access.
