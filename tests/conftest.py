"""Synthetic fixtures (no course content)."""
from __future__ import annotations

import json

import pytest

from coursedigest.models import (CourseMap, CourseNotes, Diagram, Edge, Example, Flashcard, KeyIdea, LessonMeta,
                                 LessonNotes, Module, ModuleOverview, Node, Term, WatchMoment)


def next_data_html(queries: list[tuple[list[str], dict | None]]) -> str:
    data = {"props": {"pageProps": {"trpcState": {"json": {"queries": [
        {"queryKey": [key, {"type": "query"}], "state": {"data": value}} for key, value in queries]}}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


COURSE = {
    "slug": "demo-course", "name": "Demo Course", "totalDurationSeconds": 1800,
    "listing": [
        {"moduleLabel": "Module 1", "name": "Basics", "content": [{"key": "aa1", "type": "lesson"}, {"key": "aa2", "type": "lesson"}]},
        {"moduleLabel": "Module 2", "name": "Practice", "content": [{"key": "bb1", "type": "lesson"}, {"key": "bb2", "type": "lesson"},
                                                                   {"key": "bb3", "type": "lesson"}]},
    ],
    "lessons": {
        "aa1": {"index": 1, "name": "Welcome!", "type": "video", "time": 120},
        "aa2": {"index": 2, "name": "Setup: your machine", "type": "reading_material", "time": 300},
        "bb1": {"index": 3, "name": "Loops and checks", "type": "video", "time": 400},
        "bb2": {"index": 4, "name": "Ungraded Lab: Try it", "type": "notebook", "time": 900},
        "bb3": {"index": 5, "name": "Module 2 quiz", "type": "quiz", "time": 600},
    },
}


@pytest.fixture
def course_html() -> str:
    return next_data_html([(["course", "getCourseBySlug"], COURSE), (["user", "getUserProfile"], {"id": 1}),
                           (["course", "getLessonVideoSubtitle"], {"captions": [
                               {"startInSeconds": 2, "endInSeconds": 6, "text": " First line. "},
                               {"startInSeconds": 65, "endInSeconds": 70, "text": "Second line."}]})])


def diagram(kind: str = "flow") -> Diagram:
    nodes = [Node(id=f"n{i}", label=f"Step {i} <b>", note="a short note" if i == 1 else "",
                  group="Left" if i % 2 else "Right") for i in range(1, 5)]
    edges = [Edge(source="n1", target="n2", label="then"), Edge(source="n2", target="n3", label=""),
             Edge(source="n3", target="n4", label=""), Edge(source="n4", target="n2", label="retry")]
    return Diagram(kind=kind, title="How it works", nodes=nodes, edges=edges)


def lesson_notes(importance: str = "must") -> LessonNotes:
    return LessonNotes(
        importance=importance, importance_reason="Core idea.", tldr="Loops make outputs better.",
        summary="The lesson shows a loop.", key_ideas=[KeyIdea(idea="Iterate", detail="Draft, check, revise.")],
        example=Example(title="Essay", scenario="Write an essay.", steps=["Draft", "Critique", "Revise"], takeaway="Better."),
        diagram=diagram("cycle"), watch=[WatchMoment(start=3, end=60, why="Slide"), WatchMoment(start=500, end=600, why="Out of range")],
        terms=[Term(term="Reflection", definition="Checking your own output.")],
        flashcards=[Flashcard(q="Why loop?", a="To improve quality.")],
    )


def course_notes() -> CourseNotes:
    return CourseNotes(big_picture="A course about loops.", top_takeaways=["Loop.", "Measure."],
                       concept_map=diagram("hub"), module_overviews=[ModuleOverview(module="Basics", one_liner="Start here.")])


@pytest.fixture
def course_map() -> CourseMap:
    lessons = {slug: LessonMeta(index=v["index"], slug=slug, name=v["name"], type=v["type"], seconds=v["time"],
                                module="Module 1 - Basics" if slug.startswith("aa") else "Module 2 - Practice")
               for slug, v in COURSE["lessons"].items()}
    return CourseMap(slug="demo-course", name="Demo Course", total_seconds=1800,
                     modules=[Module(label="Module 1", name="Basics", lessons=["aa1", "aa2"]),
                              Module(label="Module 2", name="Practice", lessons=["bb1", "bb2", "bb3"])],
                     lessons=lessons)


class FakeLLM:
    """Stands in for coursedigest.llm.LLM: returns canned objects per output type."""

    model = "fake-model"

    def __init__(self, fail_on: str = ""):
        self.fail_on = fail_on
        self.prompts: list[str] = []

    def structured(self, system, user, output, cache_dir, key):
        self.prompts.append(user)
        if self.fail_on and self.fail_on in user:
            raise RuntimeError("boom")
        if output is LessonNotes:
            return lesson_notes()
        if output is CourseNotes:
            return course_notes()
        raise AssertionError(output)

    def label(self) -> str:
        return self.model
