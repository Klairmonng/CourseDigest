# Senior Engineer - coursedigest-v1
- **fetch:** `context.request.get(lesson_url)` (shares the profile's cookies, no rendering) + regex for `__NEXT_DATA__`; find tRPC queries by key name (`getCourseBySlug`, `getLessonVideoSubtitle`), never by index. Labs need a real page: `page.goto`, wait for `iframe[src*="/notebooks/"]`, derive base URL, token and folder from its src, walk `/api/contents/<folder>`, download `/files/...`.
- **claude/digest:** `client.messages.parse` with the pydantic model per the claude-api skill; stable system prompt for caching; lesson content inside `<transcript>` tags; clamp watch timestamps to the caption range after parsing.
- **shim:** patch class methods (`openai.resources.responses.Responses.create`, `openai.resources.chat.completions.Completions.create`, `anthropic.resources.messages.Messages.create`, aisuite's completions) and keep the translation in pure functions for tests.
- **labs:** nbconvert subprocess with env (`IPYTHONDIR`, `COURSEDIGEST_TRACE`, `COURSEDIGEST_MODEL`, keys); count outputs with `output_type == "error"`.
- **site:** one pure layout function per diagram kind returning SVG; the template embeds data as JSON for filter, search and flashcards.
- **Tricky:** Windows paths and encodings; the nbconvert kernel must be the labs venv's python.
