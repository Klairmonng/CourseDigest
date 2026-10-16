import base64

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


def test_images_written_to_disk_are_added_once(tmp_path):
    names = labs.save_images(notebook(), tmp_path / "outputs")
    (tmp_path / "generated_image.png").write_bytes(b"new picture")
    (tmp_path / "same_as_cell.png").write_bytes(base64.b64decode(PNG))
    all_names = labs.save_written_images(tmp_path, 0, names)
    added = all_names[len(names):]
    assert len(added) == 1 and added[0].startswith("file-generated_image-")
    assert (tmp_path / "outputs" / added[0]).read_bytes() == b"new picture"


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


def test_services_come_from_the_lab_config(tmp_path, monkeypatch):
    assert labs.start_services(tmp_path / "python", tmp_path, {}) == ([], {})
    (tmp_path / "coursedigest.json").write_text(
        '{"services": [{"app": "srv:app", "port": 8765}], "env": {"API_URL": "http://127.0.0.1:8765"}}', "utf-8")
    started = []
    monkeypatch.setattr(labs.subprocess, "Popen", lambda command, **kw: started.append(command) or "proc")
    monkeypatch.setattr(labs, "wait_for_port", lambda port: None)
    processes, env = labs.start_services(tmp_path / "python", tmp_path, {})
    assert processes == ["proc"] and env == {"API_URL": "http://127.0.0.1:8765"}
    assert started[0][-5:] == ["srv:app", "--host", "127.0.0.1", "--port", "8765"]


def test_clip():
    assert labs.clip("abc", 5) == "abc"
    assert labs.clip("abcdefgh", 3).startswith("abc ...[5 more")
