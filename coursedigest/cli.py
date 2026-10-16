"""Command line: coursedigest login | fetch | digest | labs | site | all."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .fetch import FetchError, course_slug
from .llm import LLMError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coursedigest", description="Digest a DeepLearning.AI course into a visual study site.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project folder (default: current folder)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="sign in to DeepLearning.AI in a browser window (once)")
    fetch = commands.add_parser("fetch", help="download lessons and ungraded labs")
    fetch.add_argument("course", help="course URL or slug")
    fetch.add_argument("--force", action="store_true", help="download again even if cached")
    fetch.add_argument("--no-labs", action="store_true", help="skip lab downloads")
    for name, text in (("digest", "write lesson notes with the model"), ("labs", "run the ungraded labs and explain them"),
                       ("site", "build the visual site"), ("all", "fetch, digest, labs and site")):
        command = commands.add_parser(name, help=text)
        command.add_argument("course", help="course URL or slug")
        if name == "labs":
            command.add_argument("--only", nargs="+", metavar="PREFIX", help="lab folders to run, e.g. 25 44")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpx2", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root = args.root.resolve()
    load_dotenv(root / ".env")
    try:
        return run(args, root)
    except (FetchError, LLMError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def run(args: argparse.Namespace, root: Path) -> int:
    if args.command == "login":
        from .fetch import login
        print("Sign in to DeepLearning.AI in the window that opens, then close the window.")
        login(root)
        print("Saved. You can now run: coursedigest fetch <course-url>")
        return 0

    slug = course_slug(args.course)
    if args.command in ("fetch", "all"):
        from .fetch import fetch_course
        course = fetch_course(args.course, root, force=getattr(args, "force", False),
                              with_labs=not getattr(args, "no_labs", False))
        print(f"Fetched {course.name}: {len(course.lessons)} lessons")
    if args.command in ("digest", "labs", "all"):
        from .llm import LLM
        llm = LLM()
        if args.command in ("digest", "all"):
            from .digest import digest_course
            digest = digest_course(slug, root, llm)
            failed = [d.title for d in digest.lessons if d.status != "ok"]
            print(f"Digested {len(digest.lessons) - len(failed)}/{len(digest.lessons)} lessons"
                  + (f"; not digested: {', '.join(failed)}" if failed else ""))
        if args.command in ("labs", "all"):
            from .labs import run_labs
            for walkthrough in run_labs(slug, root, llm, getattr(args, "only", None)):
                print(f"Lab {walkthrough.title}: {walkthrough.run.status} "
                      f"({walkthrough.run.errors} cell errors, {walkthrough.run.calls} model calls)")
        print(f"Model usage this run: {llm.summary()}")
    if args.command in ("site", "all"):
        from .site import build_site
        print(f"Site: {build_site(slug, root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
