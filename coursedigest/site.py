"""Static site: one self-contained index.html per course; diagrams are drawn as inline SVG."""
from __future__ import annotations

import json
import math
import re
import shutil
from dataclasses import dataclass
from html import escape
from pathlib import Path

from jinja2 import Environment, PackageLoader
from markupsafe import Markup

from .models import CourseDigest, Diagram, LabWalkthrough, Node

CHAR = 7.0  # average glyph width at 13px
NOTE_CHAR = 6.2  # at 11.5px
LINE = 17
NOTE_LINE = 15
PAD = 10
READ_WPM = 220
IMAGE_REF = re.compile(r"\[image: assets/([^\]]+)\]")


# --- diagrams ----------------------------------------------------------------------------------

def wrap(text: str, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + [line] if line else lines


@dataclass
class Box:
    node: Node
    x: float
    y: float
    w: float
    h: float
    label: list[str]
    note: list[str]

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def edge_point(self, toward_x: float, toward_y: float) -> tuple[float, float]:
        dx, dy = toward_x - self.cx, toward_y - self.cy
        if dx == 0 and dy == 0:
            return self.cx, self.cy
        scale = min(self.w / 2 / abs(dx) if dx else math.inf, self.h / 2 / abs(dy) if dy else math.inf)
        return self.cx + dx * scale, self.cy + dy * scale


def make_box(node: Node, width: float, x: float = 0, y: float = 0) -> Box:
    label = wrap(node.label, int((width - 2 * PAD) / CHAR)) or [""]
    note = wrap(node.note, int((width - 2 * PAD) / NOTE_CHAR))
    height = 2 * PAD + len(label) * LINE + (len(note) * NOTE_LINE + 4 if note else 0)
    return Box(node, x, y, width, height, label, note)


def box_svg(box: Box, extra: str = "") -> str:
    parts = [f'<rect class="dg-box{extra}" x="{box.x:.0f}" y="{box.y:.0f}" width="{box.w:.0f}" '
             f'height="{box.h:.0f}" rx="8"/>']
    y = box.y + PAD + 13
    for line in box.label:
        parts.append(f'<text class="dg-label" x="{box.cx:.0f}" y="{y:.0f}" text-anchor="middle">{escape(line)}</text>')
        y += LINE
    y += 4 if box.note else 0
    for line in box.note:
        parts.append(f'<text class="dg-note" x="{box.cx:.0f}" y="{y - 2:.0f}" text-anchor="middle">{escape(line)}</text>')
        y += NOTE_LINE
    return "".join(parts)


def label_svg(x: float, y: float, text: str) -> str:
    return f'<text class="dg-edge-label" x="{x:.0f}" y="{y:.0f}" text-anchor="middle">{escape(text)}</text>' if text else ""


def arrow(a: Box, b: Box, text: str = "") -> str:
    x1, y1 = a.edge_point(b.cx, b.cy)
    x2, y2 = b.edge_point(a.cx, a.cy)
    return (f'<line class="dg-edge" x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
            f'marker-end="url(#cd-arrow)"/>' + label_svg((x1 + x2) / 2, (y1 + y2) / 2 - 4, text))


def edges_by_id(diagram: Diagram, boxes: dict[str, Box]) -> list[tuple[Box, Box, str]]:
    return [(boxes[e.source], boxes[e.target], e.label) for e in diagram.edges
            if e.source in boxes and e.target in boxes and e.source != e.target]


def layout_flow(diagram: Diagram) -> tuple[str, float, float]:
    margin, width, gap = 70, 300, 34
    boxes, y = {}, 10
    for node in diagram.nodes:
        boxes[node.id] = make_box(node, width, margin, y)
        y += boxes[node.id].h + gap
    order = [n.id for n in diagram.nodes]
    edges = edges_by_id(diagram, boxes) or [(boxes[a], boxes[b], "") for a, b in zip(order, order[1:])]
    parts = []
    for a, b, text in edges:
        ia, ib = order.index(a.node.id), order.index(b.node.id)
        if ib == ia + 1:
            parts.append(f'<line class="dg-edge" x1="{a.cx:.0f}" y1="{a.y + a.h:.0f}" x2="{b.cx:.0f}" y2="{b.y:.0f}" '
                         f'marker-end="url(#cd-arrow)"/>' + label_svg(a.cx + 46, (a.y + a.h + b.y) / 2 + 4, text))
        else:  # loop back (left) or skip ahead (right)
            side = margin if ib < ia else margin + width
            out = -48 if ib < ia else 48
            parts.append(f'<path class="dg-edge dg-loop" d="M{side:.0f},{a.cy:.0f} C{side + out:.0f},{a.cy:.0f} '
                         f'{side + out:.0f},{b.cy:.0f} {side:.0f},{b.cy:.0f}" marker-end="url(#cd-arrow)"/>'
                         + label_svg(side + out * 0.9, (a.cy + b.cy) / 2, text))
    body = "".join(parts) + "".join(box_svg(b) for b in boxes.values())
    return body, margin * 2 + width, y - gap + 10


def ring(diagram: Diagram, nodes: list[Node], width: float, center_extra: float = 0) -> tuple[dict[str, Box], float]:
    radius = max(120.0, len(nodes) * 34.0) + center_extra
    boxes = {}
    for i, node in enumerate(nodes):
        angle = -math.pi / 2 + 2 * math.pi * i / max(1, len(nodes))
        box = make_box(node, width)
        box.x = radius * math.cos(angle) - width / 2
        box.y = radius * 0.78 * math.sin(angle) - box.h / 2
        boxes[node.id] = box
    return boxes, radius


def shift(boxes: list[Box]) -> tuple[float, float]:
    min_x, min_y = min(b.x for b in boxes) - 20, min(b.y for b in boxes) - 20
    for b in boxes:
        b.x -= min_x
        b.y -= min_y
    return max(b.x + b.w for b in boxes) + 20, max(b.y + b.h for b in boxes) + 20


def layout_cycle(diagram: Diagram) -> tuple[str, float, float]:
    boxes, _ = ring(diagram, diagram.nodes, 150)
    width, height = shift(list(boxes.values()))
    order = [n.id for n in diagram.nodes]
    edges = edges_by_id(diagram, boxes) or [(boxes[a], boxes[b], "") for a, b in zip(order, order[1:] + order[:1])]
    body = "".join(arrow(a, b, t) for a, b, t in edges) + "".join(box_svg(b) for b in boxes.values())
    return body, width, height


def layout_hub(diagram: Diagram) -> tuple[str, float, float]:
    center, spokes = diagram.nodes[0], diagram.nodes[1:]
    boxes, _ = ring(diagram, spokes, 150, center_extra=30)
    hub = make_box(center, 170)
    hub.x, hub.y = -hub.w / 2, -hub.h / 2
    boxes[center.id] = hub
    width, height = shift(list(boxes.values()))
    lines = []
    for spoke in spokes:
        b = boxes[spoke.id]
        x1, y1 = hub.edge_point(b.cx, b.cy)
        x2, y2 = b.edge_point(hub.cx, hub.cy)
        lines.append(f'<line class="dg-spoke" x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}"/>')
    labelled = [(a, b, t) for a, b, t in edges_by_id(diagram, boxes) if t]
    body = ("".join(lines) + "".join(label_svg((a.cx + b.cx) / 2, (a.cy + b.cy) / 2, t) for a, b, t in labelled)
            + "".join(box_svg(b, " dg-hub" if b is hub else "") for b in boxes.values()))
    return body, width, height


def layout_compare(diagram: Diagram) -> tuple[str, float, float]:
    width, gap = 200, 22
    groups: dict[str, list[Node]] = {}
    for node in diagram.nodes:
        groups.setdefault(node.group or "Other", []).append(node)
    parts, height = [], 0.0
    for col, (group, nodes) in enumerate(groups.items()):
        x = 10 + col * (width + gap)
        parts.append(f'<text class="dg-group" x="{x + width / 2:.0f}" y="24" text-anchor="middle">{escape(group)}</text>')
        y = 38
        for node in nodes:
            box = make_box(node, width, x, y)
            parts.append(box_svg(box))
            y += box.h + 12
        height = max(height, y)
    return "".join(parts), 20 + len(groups) * (width + gap) - gap, height + 4


def layout_layers(diagram: Diagram) -> tuple[str, float, float]:
    width, gap = 460, 22
    boxes, y = {}, 10
    for node in diagram.nodes:
        boxes[node.id] = make_box(node, width, 10, y)
        y += boxes[node.id].h + gap
    order = [n.id for n in diagram.nodes]
    parts = [f'<line class="dg-edge" x1="{a.cx:.0f}" y1="{a.y + a.h:.0f}" x2="{b.cx:.0f}" y2="{b.y:.0f}" '
             f'marker-end="url(#cd-arrow)"/>' for a, b, _ in edges_by_id(diagram, boxes)
             if abs(order.index(a.node.id) - order.index(b.node.id)) == 1]
    return "".join(parts) + "".join(box_svg(b, " dg-layer") for b in boxes.values()), width + 20, y - gap + 10


LAYOUTS = {"flow": layout_flow, "cycle": layout_cycle, "hub": layout_hub, "compare": layout_compare,
           "layers": layout_layers}


def render_diagram(diagram: Diagram | None) -> Markup:
    if not diagram or not diagram.nodes:
        return Markup("")
    body, width, height = LAYOUTS[diagram.kind](diagram)
    return Markup(f'<svg class="dg dg-{diagram.kind}" viewBox="0 0 {width:.0f} {height:.0f}" '
                  f'style="max-width:{width:.0f}px" role="img" aria-label="{escape(diagram.title)}">{body}</svg>')


# --- page --------------------------------------------------------------------------------------

def glossary(digest: CourseDigest) -> list[dict]:
    terms: dict[str, dict] = {}
    for lesson in digest.lessons:
        for term in lesson.notes.terms if lesson.notes else []:
            terms.setdefault(term.term.lower(), {"term": term.term, "definition": term.definition, "lesson": lesson.title})
    return sorted(terms.values(), key=lambda t: t["term"].lower())


def flashcards(digest: CourseDigest) -> list[dict]:
    return [{"q": card.q, "a": card.a, "lesson": lesson.title, "importance": lesson.notes.importance}
            for lesson in digest.lessons if lesson.notes for card in lesson.notes.flashcards]


def read_minutes(digest: CourseDigest) -> int:
    words = 0
    for lesson in digest.lessons:
        if lesson.notes:
            n = lesson.notes
            words += len(" ".join([n.tldr, n.summary, n.example.scenario, n.example.takeaway, *n.example.steps,
                                   *(k.idea + " " + k.detail for k in n.key_ideas)]).split())
    return max(1, round(words / READ_WPM))


def load_labs(course_dir: Path) -> list[tuple[LabWalkthrough, list[dict]]]:
    labs = []
    for path in sorted(course_dir.glob("*/walkthrough.json")):
        walkthrough = LabWalkthrough.model_validate_json(path.read_text("utf-8"))
        trace_path = path.parent / "trace.jsonl"
        trace = [json.loads(line) for line in trace_path.read_text("utf-8").splitlines() if line.strip()] \
            if trace_path.exists() else []
        labs.append((walkthrough, trace))
    return labs


def copy_lab_assets(lab_dir: Path, out: Path) -> None:
    for sub in ("outputs", "assets"):
        if (lab_dir / sub).exists():
            shutil.copytree(lab_dir / sub, out / "assets" / lab_dir.name / sub, dirs_exist_ok=True)


def trace_view(folder: str, trace: list[dict]) -> list[dict]:
    """Trace entries for the page: image references pointed at the copied assets, long text clipped."""
    def fix(text: str) -> str:
        text = text if len(text) <= 3000 else text[:3000] + " ..."
        return IMAGE_REF.sub(lambda m: f"[image: assets/{folder}/assets/{m.group(1)}]", text)
    return [{"i": t["i"], "api": t["api"], "requested_model": t["requested_model"], "ms": t["ms"],
             "error": t["error"], "system": fix(t.get("system") or ""),
             "input": fix(t["messages"][-1]["content"]) if t["messages"] else "",
             "output": fix(t["output"]), "tool_calls": t["tool_calls"], "usage": t["usage"]} for t in trace]


def build_site(slug: str, root: Path) -> Path:
    digest = CourseDigest.model_validate_json((root / "digests" / f"{slug}.json").read_text("utf-8"))
    out = root / "site" / slug
    out.mkdir(parents=True, exist_ok=True)
    labs = load_labs(root / "labs" / slug)
    for walkthrough, _ in labs:
        copy_lab_assets(root / "labs" / slug / walkthrough.folder, out)
    env = Environment(loader=PackageLoader("coursedigest", "templates"), autoescape=True)
    env.filters["diagram"] = render_diagram
    env.filters["clock"] = lambda s: f"{int(s) // 60}:{int(s) % 60:02d}"
    lab_slugs = {w.slug for w, _ in labs}
    html = env.get_template("site.html.j2").render(
        digest=digest, course=digest.course, notes=digest.notes,
        lessons={l.slug: l for l in digest.lessons}, labs=labs, lab_slugs=lab_slugs,
        glossary=glossary(digest), read_minutes=read_minutes(digest),
        video_minutes=round(digest.course.total_seconds / 60),
        data=Markup(json.dumps({"flashcards": flashcards(digest),
                                "traces": {w.folder: trace_view(w.folder, t) for w, t in labs}},
                               ensure_ascii=False).replace("</", "<\\/")),
    )
    (out / "index.html").write_text(html, "utf-8")
    return out / "index.html"
