"""
Graph Layout Agent
------------------
Pure Python (no LLM).
Converts the annotated knowledge-tree into a NODES list with x/y positions,
radii, colors, and connection lists ready for the SVG renderer.
"""
import math
import re

# ── Visual config ─────────────────────────────────────────────────────────────
CANVAS_W = 1400
CANVAS_H = 900
CX = CANVAS_W / 2
CY = CANVAS_H / 2

RADII = {"root": 88, "chapter": 63, "section": 45, "sub": 33}
COLORS = {
    "root":    "#0ea5e9",
    "chapter": "#7c3aed",
    "section": "#3b82f6",
    "sub":     "#f59e0b",
}
FLOATS = ["float-a", "float-b", "float-c"]

# Distance from parent center at each level
RING_RADIUS = {1: 290, 2: 160, 3: 90}


def _make_id(title: str, prefix: str = "") -> str:
    """Turn a title into a safe DOM id."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{prefix}{slug}" if prefix else slug


class GraphLayoutAgent:
    """Agent that computes the node positions and builds the NODES JSON array."""

    def build(self, structure: dict, lesson_title: str, file_names: list) -> dict:
        """
        Args:
            structure: Annotated tree from StructureAgent + QuizAgent.
            lesson_title: Human-readable lesson title.
            file_names: List of uploaded PDF filenames.

        Returns:
            dict with keys: nodes, lesson_title, files
        """
        nodes = []
        node_index = {}  # id → node dict (for mutation)

        # ── Root node ─────────────────────────────────────────────────────────
        root_emoji = structure.get("emoji", "📚")
        root_id = "root"
        root_node = {
            "id": root_id,
            "label": root_emoji,
            "sublabel": self._wrap(lesson_title, 12),
            "type": "root",
            "level": 0,
            "x": CX,
            "y": CY,
            "r": RADII["root"],
            "color": COLORS["root"],
            "float": FLOATS[0],
            "unlocked": True,
            "mastered": False,
            "summary": structure.get("summary", "The root of your knowledge graph."),
            "quiz": structure.get("quiz"),
            "connections": [],
        }
        nodes.append(root_node)
        node_index[root_id] = root_node

        chapters = structure.get("chapters", [])
        n_chapters = len(chapters)

        for ch_i, chapter in enumerate(chapters):
            # ── Chapter node ──────────────────────────────────────────────────
            ch_angle = (2 * math.pi / n_chapters) * ch_i - math.pi / 2
            ch_r = RING_RADIUS[1]
            ch_x = CX + ch_r * math.cos(ch_angle)
            ch_y = CY + ch_r * math.sin(ch_angle)

            ch_id = _make_id(chapter["title"], "ch-")
            ch_node = {
                "id": ch_id,
                "label": chapter.get("emoji", "📖"),
                "sublabel": self._wrap(chapter["title"], 10),
                "type": "chapter",
                "level": 1,
                "x": ch_x,
                "y": ch_y,
                "r": RADII["chapter"],
                "color": COLORS["chapter"],
                "float": FLOATS[ch_i % 3],
                # Keep the first chapter open from the start for easier entry.
                "unlocked": ch_i == 0,
                "mastered": False,
                "summary": chapter.get("summary", ""),
                "quiz": chapter.get("quiz"),
                "connections": [root_id],
            }
            nodes.append(ch_node)
            node_index[ch_id] = ch_node

            # Wire root ↔ chapter
            root_node["connections"].append(ch_id)

            sections = chapter.get("sections", [])
            n_sections = len(sections)

            for sec_i, section in enumerate(sections):
                # ── Section node ──────────────────────────────────────────────
                # Spread sections in a fan around the chapter's direction
                if n_sections == 1:
                    spread = 0.0
                else:
                    spread = math.pi * 0.6  # 108° fan
                base_angle = ch_angle
                sec_angle = base_angle - spread / 2 + (spread / (n_sections - 1 or 1)) * sec_i
                sec_r = RING_RADIUS[2]
                sec_x = ch_x + sec_r * math.cos(sec_angle)
                sec_y = ch_y + sec_r * math.sin(sec_angle)

                sec_id = _make_id(section["title"], f"sec-{ch_i}-")
                sec_node = {
                    "id": sec_id,
                    "label": section.get("emoji", "🔍"),
                    "sublabel": self._wrap(section["title"], 8),
                    "type": "section",
                    "level": 2,
                    "x": sec_x,
                    "y": sec_y,
                    "r": RADII["section"],
                    "color": COLORS["section"],
                    "float": FLOATS[(ch_i + sec_i) % 3],
                    "unlocked": False,
                    "mastered": False,
                    "summary": section.get("summary", ""),
                    "quiz": section.get("quiz"),
                    "connections": [ch_id],
                }
                nodes.append(sec_node)
                node_index[sec_id] = sec_node

                # Wire chapter ↔ section
                ch_node["connections"].append(sec_id)

                subsections = section.get("subsections", [])
                n_subs = len(subsections)

                for sub_i, sub in enumerate(subsections):
                    # ── Subsection node ───────────────────────────────────────
                    if n_subs == 1:
                        sub_spread = 0.0
                    else:
                        sub_spread = math.pi * 0.5
                    sub_angle = sec_angle - sub_spread / 2 + (sub_spread / (n_subs - 1 or 1)) * sub_i
                    sub_r = RING_RADIUS[3]
                    sub_x = sec_x + sub_r * math.cos(sub_angle)
                    sub_y = sec_y + sub_r * math.sin(sub_angle)

                    sub_id = _make_id(sub["title"], f"sub-{ch_i}-{sec_i}-")
                    sub_node = {
                        "id": sub_id,
                        "label": sub.get("emoji", "📌"),
                        "sublabel": self._wrap(sub["title"], 8),
                        "type": "sub",
                        "level": 3,
                        "x": sub_x,
                        "y": sub_y,
                        "r": RADII["sub"],
                        "color": COLORS["sub"],
                        "float": FLOATS[(ch_i + sec_i + sub_i) % 3],
                        "unlocked": False,
                        "mastered": False,
                        "summary": sub.get("summary", ""),
                        "quiz": sub.get("quiz"),
                        "connections": [sec_id],
                    }
                    nodes.append(sub_node)
                    node_index[sub_id] = sub_node

                    # Wire section ↔ subsection
                    sec_node["connections"].append(sub_id)

        return {
            "nodes": nodes,
            "lesson_title": lesson_title,
            "files": file_names,
        }

    @staticmethod
    def _wrap(text: str, max_len: int) -> str:
        """Add a newline in the middle of long text for sublabels."""
        if len(text) <= max_len:
            return text
        words = text.split()
        half = len(words) // 2
        return " ".join(words[:half]) + "\n" + " ".join(words[half:])
