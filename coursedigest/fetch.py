"""DeepLearning.AI fetcher: course map, captions and readings from `__NEXT_DATA__`, ungraded lab folders."""
from __future__ import annotations

import json
import logging
import posixpath
import re
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .models import LAB_TYPES, TEXT_TYPES, Caption, CourseMap, LabInfo, LessonContent, LessonMeta, Module

BASE = "https://learn.deeplearning.ai"
PROFILE_DIR = ".profile"
PAUSE_SECONDS = 1.0
LAB_TIMEOUT_MS = 120_000
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
PACKAGE_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*(\[[A-Za-z0-9_,\-]+\])?\s*([<>=!~]=?\s*[\w.*]+)?\s*$")
GRADED = re.compile(r"(?<!un)graded|assignment|autograder", re.I)

log = logging.getLogger(__name__)


class FetchError(RuntimeError):
    pass


class NotLoggedIn(FetchError):
    pass


# --- pure parsing ------------------------------------------------------------------------------

def course_slug(arg: str) -> str:
    match = re.search(r"/courses/([^/?#]+)", arg)
    return match.group(1) if match else arg.strip("/")


def title_slug(name: str) -> str:
    """The lesson URL suffix the site uses (JavaScript encodeURIComponent of the dashed name)."""
    return quote(name.lower().replace(" ", "-"), safe="-_.!~*'()")


def lesson_url(course: str, meta: LessonMeta) -> str:
    return f"{BASE}/courses/{course}/lesson/{meta.slug}/{title_slug(meta.name)}"


def parse_next_data(html: str) -> dict:
    match = NEXT_DATA.search(html)
    if not match:
        raise FetchError("page has no __NEXT_DATA__ (signed out, or the site changed)")
    return json.loads(match.group(1))


def query(data: dict, router: str, procedure: str):
    """State of the tRPC query `router.procedure` embedded in the page, or None."""
    try:
        queries = data["props"]["pageProps"]["trpcState"]["json"]["queries"]
    except (KeyError, TypeError) as exc:
        raise FetchError(f"page data has no tRPC state ({exc})") from exc
    for item in queries:
        key = item.get("queryKey") or []
        if key and key[0] == [router, procedure]:
            return (item.get("state") or {}).get("data")
    return None


def logged_in(data: dict) -> bool:
    return bool(query(data, "user", "getUserProfile"))


def course_map(data: dict) -> CourseMap:
    course = query(data, "course", "getCourseBySlug")
    if not course:
        raise FetchError("course.getCourseBySlug missing from page data")
    modules, module_of = [], {}
    for entry in course.get("listing") or []:
        label, name = entry.get("moduleLabel") or "", entry.get("name") or ""
        keys = [item["key"] for item in entry.get("content") or [] if item.get("type") == "lesson"]
        modules.append(Module(label=label, name=name, lessons=keys))
        for key in keys:
            module_of[key] = " - ".join(part for part in (label, name) if part)
    lessons = {
        slug: LessonMeta(index=raw["index"], slug=slug, name=raw["name"], type=raw["type"],
                         seconds=int(raw.get("time") or 0), module=module_of.get(slug, ""))
        for slug, raw in (course.get("lessons") or {}).items()
    }
    return CourseMap(slug=course["slug"], name=course["name"],
                     total_seconds=int(course.get("totalDurationSeconds") or 0),
                     modules=modules, lessons=lessons)


def captions(data: dict) -> list[Caption] | None:
    subtitle = query(data, "course", "getLessonVideoSubtitle") or {}
    rows = subtitle.get("captions") or []
    return [Caption(start=row["startInSeconds"], end=row["endInSeconds"], text=row["text"].strip())
            for row in rows] or None


def reading(data: dict) -> str | None:
    return (query(data, "course", "getReadingMaterial") or {}).get("content") or None


def lab_location(src: str) -> tuple[str, str, str]:
    """(server base URL, token, notebook path) from the lab iframe's src."""
    url = urlparse(src)
    if "/notebooks/" not in url.path:
        raise FetchError("lab iframe does not point at a notebook")
    token = parse_qs(url.query).get("token", [""])[0]
    notebook = unquote(url.path.split("/notebooks/", 1)[1])
    return f"{url.scheme}://{url.netloc}", token, notebook


def is_graded(path: str) -> bool:
    return bool(GRADED.search(path))


def requirements_from_markdown(markdown: str) -> list[str] | None:
    """The first fenced block that reads like a requirements.txt (>= 5 package lines)."""
    for block in re.findall(r"```[^\n]*\n(.*?)```", markdown, re.S):
        lines = [line.strip() for line in block.splitlines() if line.strip() and not line.strip().startswith("#")]
        packages = [line for line in lines if PACKAGE_LINE.match(line)]
        if len(packages) >= 5 and len(packages) == len(lines):
            return packages
    return None


def safe_relative(path: str, root: str) -> str:
    rel = posixpath.relpath(path, root) if root else path
    if rel.startswith("..") or posixpath.isabs(rel):
        raise FetchError(f"refusing path outside the lab folder: {path}")
    return rel


# --- browser I/O -------------------------------------------------------------------------------

@contextmanager
def browser(root: Path, headless: bool = True):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(root / PROFILE_DIR), headless=headless)
        try:
            yield context
        finally:
            context.close()


def login(root: Path) -> None:
    """Open the site in a visible browser; returns when the user closes the window."""
    with browser(root, headless=False) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(BASE)
        page.wait_for_event("close", timeout=0)


def page_data(context, url: str) -> dict:
    response = context.request.get(url)
    time.sleep(PAUSE_SECONDS)
    if not response.ok:
        raise FetchError(f"{url}: HTTP {response.status}")
    return parse_next_data(response.text())


def fetch_course(arg: str, root: Path, force: bool = False, with_labs: bool = True) -> CourseMap:
    slug = course_slug(arg)
    cache = root / "cache" / slug
    (cache / "lessons").mkdir(parents=True, exist_ok=True)
    with browser(root) as context:
        data = page_data(context, f"{BASE}/courses/{slug}")
        if not logged_in(data):
            raise NotLoggedIn("not signed in: run `coursedigest login` first")
        course = course_map(data)
        (cache / "course.json").write_text(course.model_dump_json(indent=2), "utf-8")
        for meta in course.ordered():
            if meta.type in TEXT_TYPES:
                fetch_lesson(context, course, meta, cache / "lessons", force)
            elif meta.type in LAB_TYPES and with_labs:
                fetch_lab(context, course, meta, root / "labs" / slug, force)
            else:
                log.info("skip %02d %s (%s)", meta.index, meta.name, meta.type)
    save_requirements(cache / "lessons", root / "labs" / slug)
    return course


def fetch_lesson(context, course: CourseMap, meta: LessonMeta, folder: Path, force: bool) -> None:
    path = folder / f"{meta.index:02d}-{meta.slug}.json"
    if path.exists() and not force:
        return
    url = lesson_url(course.slug, meta)
    data = page_data(context, url)
    content = LessonContent(meta=meta, url=url, captions=captions(data), reading=reading(data))
    if meta.type == "video" and not content.captions:
        log.warning("no captions for %02d %s", meta.index, meta.name)
    path.write_text(content.model_dump_json(indent=2), "utf-8")
    log.info("fetched %02d %s", meta.index, meta.name)


def fetch_lab(context, course: CourseMap, meta: LessonMeta, labs_root: Path, force: bool) -> None:
    if any(labs_root.glob(f"{meta.index:02d}-*/lab.json")) and not force:
        return
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    page = context.new_page()
    try:
        page.goto(lesson_url(course.slug, meta), wait_until="domcontentloaded")
        frame = page.wait_for_selector('iframe[src*="/notebooks/"]', state="attached", timeout=LAB_TIMEOUT_MS)
        src = frame.get_attribute("src") or ""
    except PlaywrightTimeout:
        log.warning("lab %02d %s: notebook did not load within %ds, skipped", meta.index, meta.name,
                    LAB_TIMEOUT_MS // 1000)
        return
    finally:
        page.close()
    base, token, notebook = lab_location(src)
    folder = posixpath.dirname(notebook)
    if is_graded(folder):
        log.warning("lab %02d %s: folder looks graded (%s), skipped", meta.index, meta.name, folder)
        return
    dest = labs_root / f"{meta.index:02d}-{posixpath.basename(folder) or meta.slug}"
    files = list_lab_files(context, base, token, folder, recursive=bool(folder))
    for path in files:
        rel = safe_relative(path, folder)
        response = context.request.get(f"{base}/files/{quote(path)}", params={"token": token})
        if not response.ok:
            raise FetchError(f"lab file {path}: HTTP {response.status}")
        target = dest.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.body())
    info = LabInfo(meta=meta, notebook=safe_relative(notebook, folder), source_dir=folder)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "lab.json").write_text(info.model_dump_json(indent=2), "utf-8")
    log.info("fetched lab %02d %s (%d files)", meta.index, meta.name, len(files))


def list_lab_files(context, base: str, token: str, folder: str, recursive: bool) -> list[str]:
    response = context.request.get(f"{base}/api/contents/{quote(folder)}", params={"content": "1", "token": token})
    if not response.ok:
        raise FetchError(f"lab listing {folder or '/'}: HTTP {response.status}")
    files = []
    for item in response.json().get("content") or []:
        name, path = item["name"], item["path"]
        if name.startswith(".") or is_graded(name):
            continue
        if item["type"] == "directory":
            if recursive:
                files += list_lab_files(context, base, token, path, recursive)
        else:
            files.append(path)
    return files


def save_requirements(lessons: Path, labs_root: Path) -> None:
    for path in sorted(lessons.glob("*.json")):
        content = LessonContent.model_validate_json(path.read_text("utf-8"))
        packages = requirements_from_markdown(content.reading or "")
        if packages:
            labs_root.mkdir(parents=True, exist_ok=True)
            (labs_root / "requirements.txt").write_text("\n".join(packages) + "\n", "utf-8")
            return
