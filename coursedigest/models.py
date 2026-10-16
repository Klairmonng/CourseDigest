"""Data contracts shared by every stage (see .10x/specs/2026-10-16-coursedigest-design.md)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TEXT_TYPES = {"video", "reading_material"}
LAB_TYPES = {"notebook", "paid_notebook"}  # ungraded only; quiz and graded_notebook are never fetched


# --- fetched course data (cache/) -------------------------------------------------------------

class LessonMeta(BaseModel):
    index: int
    slug: str
    name: str
    type: str
    seconds: int
    module: str


class Module(BaseModel):
    label: str
    name: str
    lessons: list[str]


class CourseMap(BaseModel):
    slug: str
    name: str
    total_seconds: int
    modules: list[Module]
    lessons: dict[str, LessonMeta]

    def ordered(self) -> list[LessonMeta]:
        return sorted(self.lessons.values(), key=lambda m: m.index)


class Caption(BaseModel):
    start: float
    end: float
    text: str


class LessonContent(BaseModel):
    meta: LessonMeta
    url: str
    captions: list[Caption] | None = None
    reading: str | None = None


class LabInfo(BaseModel):
    meta: LessonMeta
    notebook: str
    source_dir: str


# --- what Claude writes (every field required: structured output) -----------------------------

class Node(BaseModel):
    id: str
    label: str
    note: str
    group: str


class Edge(BaseModel):
    source: str
    target: str
    label: str


class Diagram(BaseModel):
    kind: Literal["flow", "cycle", "hub", "compare", "layers"]
    title: str
    nodes: list[Node]
    edges: list[Edge]


class KeyIdea(BaseModel):
    idea: str
    detail: str


class Example(BaseModel):
    title: str
    scenario: str
    steps: list[str]
    takeaway: str


class WatchMoment(BaseModel):
    start: int
    end: int
    why: str


class Term(BaseModel):
    term: str
    definition: str


class Flashcard(BaseModel):
    q: str
    a: str


class LessonNotes(BaseModel):
    importance: Literal["must", "good", "skip"]
    importance_reason: str
    tldr: str
    summary: str
    key_ideas: list[KeyIdea]
    example: Example
    diagram: Diagram
    watch: list[WatchMoment]
    terms: list[Term]
    flashcards: list[Flashcard]


class ModuleOverview(BaseModel):
    module: str
    one_liner: str


class CourseNotes(BaseModel):
    big_picture: str
    top_takeaways: list[str]
    concept_map: Diagram
    module_overviews: list[ModuleOverview]


class LabStep(BaseModel):
    title: str
    what_happens: str
    code_ref: str
    call_refs: list[int]
    image: str


class LabNotes(BaseModel):
    goal: str
    pattern: str
    diagram: Diagram
    steps: list[LabStep]
    results: str
    try_next: list[str]


# --- stored outputs (digests/, labs/) ---------------------------------------------------------

class LessonDigest(BaseModel):
    slug: str
    title: str
    module: str
    kind: str
    minutes: int
    url: str
    status: Literal["ok", "no_transcript", "failed"]
    error: str = ""
    notes: LessonNotes | None = None


class CourseDigest(BaseModel):
    course: CourseMap
    notes: CourseNotes | None
    lessons: list[LessonDigest]
    model: str
    prompt_version: str
    generated_at: str


class LabRun(BaseModel):
    status: Literal["ok", "errors", "failed"]
    cells: int
    errors: int
    calls: int
    input_tokens: int
    output_tokens: int
    seconds: int
    message: str = ""


class LabWalkthrough(BaseModel):
    slug: str
    title: str
    module: str
    folder: str
    run: LabRun
    images: list[str]
    notes: LabNotes | None = None
