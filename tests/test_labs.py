import nbformat

from coursedigest import labs
from coursedigest.models import LabInfo, LessonMeta

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def notebook():
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell("# Lab"),
        nbformat.v4.new_code_cell("plot()", outputs=[nbformat.v4.new_output("display_data", data={"image/png": PNG})]),
        nbformat.v4.new_code_cell("show()", outputs=[nbformat.v4.new_output(
            "display_data", data={"text/html": f'<img src="data:image/png;base64,{PNG}">'})]),
        nbformat.v4.new_code_cell("fail()", outputs=[nbformat.v4.new_output("error", ename="KeyError", evalue="'x'", traceback=[])]),
    ]
    return nb


def test_save_images_and_errors(tmp_path):
    nb = notebook()
    names = labs.save_images(nb, tmp_path / "outputs")
    assert len(names) == 2 and all((tmp_path / "outputs" / n).exists() for n in names)
    assert names[0].startswith("cell01-") and names[1].startswith("cell02-")
    assert labs.cell_errors(nb) == ["cell 3: KeyError: 'x'"]


def test_lab_prompt_lists_calls_and_errors():
    info = LabInfo(meta=LessonMeta(index=4, slug="bb2", name="Ungraded Lab: Try it", type="notebook", seconds=900,
                                   module="Module 2"), notebook="L1.ipynb", source_dir="M2/ungraded_labs/L1")
    trace = [{"i": 1, "api": "openai.chat", "requested_model": "gpt-4.1", "error": "", "output": "draft v1",
              "messages": [{"role": "user", "content": "Write"}], "tool_calls": []}]
    prompt = labs.lab_prompt(info, notebook(), ["cell01-a.png"], ["cell 3: KeyError"], trace)
    assert "#1 openai.chat (asked for gpt-4.1)" in prompt and "cell01-a.png" in prompt and "KeyError" in prompt
    assert prompt.index("<lab>") < prompt.index("plot()") < prompt.index("</lab>")


def test_startup_file_loads_the_shim(tmp_path):
    ipython = labs.startup_dir(tmp_path, tmp_path / "repo")
    text = (ipython / "profile_default" / "startup" / "00-coursedigest-shim.py").read_text("utf-8")
    assert "import coursedigest.shim" in text and "sys.path.append" in text


def test_clip():
    assert labs.clip("abc", 5) == "abc"
    assert labs.clip("abcdefgh", 3).startswith("abc ...[5 more")
