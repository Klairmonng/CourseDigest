import json

import pytest

from coursedigest import digest
from coursedigest import llm as llm_module
from coursedigest.llm import LLM, LLMError, cache_key
from coursedigest.models import Caption, CourseDigest, LessonContent, LessonNotes

from .conftest import FakeLLM, lesson_notes


def write_cache(root, course_map, contents):
    cache = root / "cache" / course_map.slug
    (cache / "lessons").mkdir(parents=True)
    (cache / "course.json").write_text(course_map.model_dump_json(), "utf-8")
    for content in contents:
        (cache / "lessons" / f"{content.meta.index:02d}-{content.meta.slug}.json").write_text(content.model_dump_json(), "utf-8")


def test_lesson_prompt_has_timestamps_and_tags(course_map):
    content = LessonContent(meta=course_map.lessons["bb1"], url="u",
                            captions=[Caption(start=5, end=9, text="Hello"), Caption(start=125, end=130, text="Bye")])
    prompt = digest.lesson_prompt(course_map, content)
    assert "[0:05] Hello" in prompt and "[2:05] Bye" in prompt
    assert prompt.index("<lesson>") < prompt.index("Hello") < prompt.index("</lesson>")


def test_clamp_watch_keeps_moments_inside_captions(course_map):
    content = LessonContent(meta=course_map.lessons["bb1"], url="u",
                            captions=[Caption(start=2, end=6, text="a"), Caption(start=60, end=90, text="b")])
    kept = digest.clamp_watch(lesson_notes(), content)
    assert [(m.start, m.end) for m in kept.watch] == [(3, 60)]
    reading = LessonContent(meta=course_map.lessons["aa2"], url="u", reading="text")
    assert digest.clamp_watch(lesson_notes(), reading).watch == []


def test_digest_course_writes_digest_and_survives_a_failed_lesson(tmp_path, course_map):
    contents = [
        LessonContent(meta=course_map.lessons["aa1"], url="u1", captions=[Caption(start=0, end=5, text="Welcome")]),
        LessonContent(meta=course_map.lessons["aa2"], url="u2", reading="Install things"),
        LessonContent(meta=course_map.lessons["bb1"], url="u3", captions=None),
    ]
    write_cache(tmp_path, course_map, contents)
    result = digest.digest_course("demo-course", tmp_path, FakeLLM(fail_on="Install things"))
    assert [(l.title, l.status) for l in result.lessons] == [
        ("Welcome!", "ok"), ("Setup: your machine", "failed"), ("Loops and checks", "no_transcript")]
    assert result.notes and result.notes.big_picture
    saved = CourseDigest.model_validate_json((tmp_path / "digests" / "demo-course.json").read_text("utf-8"))
    assert saved.lessons[0].notes.tldr == "Loops make outputs better."


class ExplodingClient:
    @property
    def chat(self):
        raise AssertionError("cached answers must not call the API")


def test_structured_reads_cache_without_calling_the_api(tmp_path):
    key = cache_key("m", "v", "prompt")
    (tmp_path / f"{key}.json").write_text(lesson_notes().model_dump_json(), "utf-8")
    llm = LLM(client=ExplodingClient(), provider="gemini")
    notes = llm.structured("sys", "prompt", LessonNotes, tmp_path, key)
    assert notes.tldr == "Loops make outputs better." and llm.usage["calls"] == 0


def rate_limit(message):
    error = llm_module.openai.RateLimitError.__new__(llm_module.openai.RateLimitError)
    Exception.__init__(error, message)
    return error


def test_quota_waits_per_minute_and_moves_on_after_a_daily_limit(monkeypatch):
    waits = []
    monkeypatch.setattr(llm_module.time, "sleep", waits.append)
    outcomes = {"a": [rate_limit("Please retry in 2s. PerMinute"), rate_limit("quota PerDay exceeded")], "b": ["done"]}

    def call(model):
        outcome = outcomes[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert llm_module.call_with_quota(["a", "b"], call) == ("b", "done")
    assert waits == [3.0]


def test_quota_gives_up_when_every_model_is_spent(monkeypatch):
    def call(model):
        raise rate_limit("PerDay")

    with pytest.raises(llm_module.DailyQuota):
        llm_module.call_with_quota(["a", "b"], call)


def test_provider_settings_and_missing_key(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini-test")
    name, settings = llm_module.provider_settings("gemini")
    assert name == "gemini" and settings["models"] == ["gemini-test"] and "googleapis" in settings["base_url"]
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        LLM(provider="gemini")
    with pytest.raises(LLMError, match="unknown"):
        llm_module.provider_settings("nope")


def test_cache_key_changes_with_any_part():
    assert cache_key("a", "b") != cache_key("ab", "")
    assert cache_key("a", "b") == cache_key("a", "b")
