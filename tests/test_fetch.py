import pytest

from coursedigest import fetch


def test_course_map_orders_modules_and_names_them(course_html):
    data = fetch.parse_next_data(course_html)
    course = fetch.course_map(data)
    assert course.name == "Demo Course" and course.total_seconds == 1800
    assert [m.label for m in course.modules] == ["Module 1", "Module 2"]
    assert [m.slug for m in course.ordered()] == ["aa1", "aa2", "bb1", "bb2", "bb3"]
    assert course.lessons["bb1"].module == "Module 2 - Practice"
    assert fetch.logged_in(data)


def test_captions_and_reading(course_html):
    data = fetch.parse_next_data(course_html)
    caps = fetch.captions(data)
    assert [(c.start, c.text) for c in caps] == [(2, "First line."), (65, "Second line.")]
    assert fetch.reading(data) is None


def test_missing_next_data_and_signed_out():
    with pytest.raises(fetch.FetchError):
        fetch.parse_next_data("<html>signed out</html>")
    assert not fetch.logged_in({"props": {"pageProps": {"trpcState": {"json": {"queries": []}}}}})


def test_title_slug_matches_site_urls():
    assert fetch.title_slug("Optional: Set up your machine") == "optional%3A-set-up-your-machine"
    assert fetch.title_slug("Latency, cost?") == "latency%2C-cost%3F"
    assert fetch.title_slug("Evals (part 1)") == "evals-(part-1)"
    assert fetch.course_slug("https://learn.deeplearning.ai/courses/demo-course/lesson/x/y") == "demo-course"
    assert fetch.course_slug("demo-course") == "demo-course"


def test_lab_location_and_paths():
    base, token, notebook = fetch.lab_location(
        "https://lab.example.org/notebooks/M2/ungraded_labs/L1/L1.ipynb?token=abc&x=1")
    assert (base, token, notebook) == ("https://lab.example.org", "abc", "M2/ungraded_labs/L1/L1.ipynb")
    assert fetch.safe_relative("M2/ungraded_labs/L1/data/a.csv", "M2/ungraded_labs/L1") == "data/a.csv"
    with pytest.raises(fetch.FetchError):
        fetch.safe_relative("M2/other/a.csv", "M2/ungraded_labs/L1")
    assert fetch.is_graded("M2/assignment") and fetch.is_graded("M2/graded_labs/x") and fetch.is_graded("Graded")
    assert not fetch.is_graded("M2/ungraded_labs/L1") and not fetch.is_graded("Ungraded_Labs")


def test_login_window_is_not_automated(tmp_path):
    command = fetch.login_command("chrome.exe", tmp_path / ".profile")
    assert command[0] == "chrome.exe" and command[-1] == fetch.BASE
    assert f"--user-data-dir={tmp_path / '.profile'}" in command
    assert not any("remote-debugging" in arg or "automation" in arg for arg in command)


def test_requirements_from_markdown():
    md = "Steps:\n```bash\npip install -r requirements.txt\n```\n```txt\n# tools\naisuite==0.1.11\nanthropic\n\npydantic[email]\n" \
         "tavily-python>=0.7.12\nWikipedia\n```"
    assert fetch.requirements_from_markdown(md) == ["aisuite==0.1.11", "anthropic", "pydantic[email]",
                                                    "tavily-python>=0.7.12", "Wikipedia"]
    assert fetch.requirements_from_markdown("```\npython -m venv venv\n```") is None
