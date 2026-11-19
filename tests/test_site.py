import base64

import nbformat
import pytest

from coursedigest import labs, site
from coursedigest.models import (CourseDigest, LabInfo, LabNotes, LabRun, LabStep, LabWalkthrough, LessonDigest,
                                 LessonMeta)

from .conftest import course_notes, diagram, lesson_notes
from .test_labs import PNG


@pytest.mark.parametrize("kind", ["flow", "cycle", "hub", "compare", "layers"])
def test_every_diagram_kind_renders_escaped_svg(kind):
    svg = str(site.render_diagram(diagram(kind)))
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "Step 1 &lt;b&gt;" in svg and "<b>" not in svg
    assert "viewBox" in svg


def test_empty_diagram_renders_nothing():
    assert site.render_diagram(None) == ""


def test_wrap_respects_width():
    assert site.wrap("one two three four", 9) == ["one two", "three", "four"]


def make_digest(course_map, tldr="Loops make outputs better."):
    notes = lesson_notes().model_copy(update={"tldr": tldr})
    lessons = [LessonDigest(slug="aa1", title="Welcome!", module="Module 1 - Basics", kind="video", minutes=2, url="u",
                            status="ok", notes=notes),
               LessonDigest(slug="bb1", title="Loops and checks", module="Module 2 - Practice", kind="video", minutes=7,
                            url="u", status="failed", error="refused")]
    return CourseDigest(course=course_map, notes=course_notes(), lessons=lessons, model="m", prompt_version="v",
                        generated_at="2026-10-16T00:00:00+00:00")


def test_build_site_renders_lessons_labs_and_escapes(tmp_path, course_map):
    hostile = "</script><script>alert(1)</script>"
    (tmp_path / "digests").mkdir()
    (tmp_path / "digests" / "demo-course.json").write_text(make_digest(course_map, hostile).model_dump_json(), "utf-8")
    lab_dir = tmp_path / "labs" / "demo-course" / "04-L1"
    (lab_dir / "outputs").mkdir(parents=True)
    (lab_dir / "outputs" / "cell03-abc.png").write_bytes(b"png")
    walkthrough = LabWalkthrough(
        slug="bb2", title="Ungraded Lab: Try it", module="Module 2 - Practice", folder="04-L1",
        run=LabRun(status="errors", cells=5, errors=1, calls=2, input_tokens=10, output_tokens=5, seconds=90),
        images=["cell03-abc.png"],
        notes=LabNotes(goal="Build a loop.", pattern="reflection", diagram=diagram("flow"),
                       steps=[LabStep(title="Draft", what_happens="Writes v1.", code_ref="draft()", call_refs=[1],
                                      image="cell03-abc.png")], results="Worked.", try_next=["Change the prompt."]))
    (lab_dir / "walkthrough.json").write_text(walkthrough.model_dump_json(), "utf-8")
    meta = LessonMeta(index=4, slug="bb2", name="Ungraded Lab: Try it", type="notebook", seconds=60, module="Module 2")
    (lab_dir / "lab.json").write_text(LabInfo(meta=meta, notebook="L1.ipynb", source_dir="L1").model_dump_json(), "utf-8")
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_markdown_cell("### 3.1 Run the **query**\nSome prose."),
                nbformat.v4.new_code_cell("run_query('<x>')", execution_count=7, outputs=[
                    nbformat.v4.new_output("stream", name="stderr", text="daily free-tier quota used up for gemini-a\n"),
                    nbformat.v4.new_output("stream", name="stdout", text="total = -190571.46\n"),
                    nbformat.v4.new_output("display_data", data={
                        "text/html": '<style>.c{}</style><div class="c" onclick="x()"><b>SQL Output</b>'
                                     '<script>steal()</script><table><tr><td>blue</td></tr></table></div>'})])]
    nbformat.write(nb, lab_dir / "L1.executed.ipynb")
    (lab_dir / "trace.jsonl").write_text(
        '{"i": 1, "api": "openai.chat", "requested_model": "gpt-4.1", "ms": 1200, "error": "", "system": "", '
        '"messages": [{"role": "user", "content": "</script> [image: assets/x.png]"}], "output": "ok", '
        '"tool_calls": [], "usage": {"input_tokens": 3, "output_tokens": 1}}\n', "utf-8")

    page = site.build_site("demo-course", tmp_path).read_text("utf-8")
    assert "Welcome!" in page and "Ungraded Lab: Try it" in page and "Not digested" in page
    assert hostile not in page and "&lt;/script&gt;" in page
    assert "<\\/script>" in page  # the trace JSON cannot close the data script
    assert 'src="assets/04-L1/outputs/cell03-abc.png"' in page
    assert (tmp_path / "site" / "demo-course" / "assets" / "04-L1" / "outputs" / "cell03-abc.png").exists()
    assert 'class="chip none"' in page  # the quiz is shown as not covered
    # the executed notebook: heading, code and its real output, without the lab's markup or our quota notices
    assert "3.1 Run the query" in page and "In [7]" in page and "run_query(&#39;&lt;x&gt;&#39;)" in page
    assert "total = -190571.46" in page and "<b>SQL Output</b><table><tr><td>blue</td></tr></table>" in page
    assert "quota used up" not in page and "onclick" not in page and "steal()" not in page


def test_clean_html_keeps_structure_and_maps_images():
    raw = base64.b64decode(PNG)
    html = (f'<head><title>t</title></head><div style="x"><a href="javascript:x()">link</a>'
            f'<img src="data:image/png;base64,{PNG}"><img src="http://example.com/x.png"><span>open')
    saved = lambda src: "assets/L/outputs/a.png" if src == f"data:image/png;base64,{PNG}" else ""
    assert site.clean_html(html, saved) == ('<div>link<img src="assets/L/outputs/a.png" alt="lab output" '
                                            'loading="lazy"><span>open</span></div>')
    assert labs.output_name(3, raw, "jpeg").startswith("cell03-") and labs.output_name(3, raw, "jpeg").endswith(".jpg")


def test_glossary_dedupes_terms(course_map):
    d = make_digest(course_map)
    d.lessons.append(d.lessons[0].model_copy(update={"slug": "zz", "title": "Again"}))
    assert [t["term"] for t in site.glossary(d)] == ["Reflection"]
    assert site.read_minutes(d) >= 1
