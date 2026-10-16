# Handoff -> SDE
Build tasks 1-9 from `decisions/engineering-manager/coursedigest-v1.md` in order, following `decisions/senior-engineer/coursedigest-v1.md` and ADR-001..003. Contracts are in the spec.

Course data shape (verified 2026-10-16 in the browser): `props.pageProps.trpcState.json.queries[]` where `queryKey[0] == ["course","getCourseBySlug"]` -> `state.data.{name, slug, lessons{slug: {index, name, type, time, videoId}}, listing[{moduleLabel, name, content[{key}]}], totalDurationSeconds}` and `["course","getLessonVideoSubtitle"]` -> `state.data.captions[{startInSeconds, endInSeconds, text}]`. Lesson types seen: video, reading_material, quiz, notebook, paid_notebook, graded_notebook.
