"""
graph.py — MAÏEUTICA Knowledge Graph Builder
Adapted from GraphBuilder (blockchain project).

Node types : concept | misconception | session
Edge types : PREREQUISITE_OF | RELATED_TO | CONFUSED_WITH | HAS_MISCONCEPTION | VISITED_IN

Same pattern as GraphBuilder:
  - self.graph = nx.DiGraph()
  - build_graph() — init from LLM extraction (≡ build_graph(token_data))
  - format_for_react_force_graph() — serialise for frontend
  - get_graph_stats() — basic NetworkX metrics
  - JSON file persistence (data/{notebook_id}_graph.json)
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import networkx as nx

DATA_DIR = Path(__file__).parent.parent / "data"

BLOOM_ORDER  = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
STATUS_ORDER = ["UNKNOWN", "VISITED", "CONFUSED", "UNDERSTOOD", "MASTERED"]


# ═══════════════════════════════════════════════════════════════════════════════
#  GraphBuilder
# ═══════════════════════════════════════════════════════════════════════════════

class GraphBuilder:
    """
    Builds a NetworkX DiGraph from LLM-extracted concept data.

    Nodes  = Concepts  (with Bloom level, mastery state, etc.)
    Edges  = PREREQUISITE_OF / RELATED_TO / CONFUSED_WITH / HAS_MISCONCEPTION
    Weight = importance score (0.0-1.0)

    Equivalent to the blockchain GraphBuilder but for educational concepts
    instead of wallets/transactions.
    """

    def __init__(self, notebook_id: str):
        self.notebook_id = notebook_id
        self.graph: nx.DiGraph = nx.DiGraph()   # same field name as original
        self._sessions: List[dict] = []
        self._graph_path = DATA_DIR / f"{notebook_id}_graph.json"
        self._load()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load(self):
        if self._graph_path.exists():
            try:
                data = json.loads(self._graph_path.read_text(encoding="utf-8"))
                self.graph = nx.node_link_graph(data["graph"])
                self._sessions = data.get("sessions", [])
            except Exception:
                self.graph = nx.DiGraph()
                self._sessions = []

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "graph": nx.node_link_data(self.graph, edges="links"),
            "sessions": self._sessions,
        }
        self._graph_path.write_text(
            json.dumps(payload, default=str, ensure_ascii=False), encoding="utf-8"
        )

    # ── Build from LLM extraction ──────────────────────────────────────────────

    def build_graph(self, concepts_json: Dict, course_json: Dict) -> nx.DiGraph:
        """
        Build the graph from concept_extractor output.
        Equivalent to GraphBuilder.build_graph(token_data) in the blockchain project
        — same clear → add_nodes → add_edges pattern.

        concepts_json keys:
          essential_concepts  : list of concept dicts
          concept_hierarchy   : {"fundamental": [...], "intermediate": [...], "advanced": [...]}
          total_concepts      : int

        course_json keys:
          course_title, modules (list with prerequisites / concepts_covered)
        """
        self.graph.clear()
        self._sessions = []

        hierarchy: dict = concepts_json.get("concept_hierarchy", {})
        fundamentals:   list = hierarchy.get("fundamental", [])
        intermediates:  list = hierarchy.get("intermediate", [])
        advanced_list:  list = hierarchy.get("advanced", [])

        # ── Step 1: Add ConceptNodes ─────────────────────────────────────────
        # Equivalent to: for wallet_addr in all_wallets: self.graph.add_node(...)
        for c in concepts_json.get("essential_concepts", []):
            cid = c["concept_id"]
            hl  = "fundamental"
            if cid in intermediates:
                hl = "intermediate"
            elif cid in advanced_list:
                hl = "advanced"

            self.graph.add_node(cid, **{
                "_type":                "concept",
                "concept_id":           cid,
                "name":                 c.get("name", cid),
                "description":          c.get("description", ""),
                "importance":           c.get("importance", "importante"),
                "bloom_level":          c.get("bloom_level", "understand"),
                "bloom_reached":        "remember",
                "hierarchy_level":      hl,
                "mastery_criteria":     c.get("mastery_criteria", []),
                "common_misconceptions":c.get("common_misconceptions", []),
                "application_examples": c.get("application_examples", []),
                "assessment_indicators":c.get("assessment_indicators", []),
                "source_chunks":        [],
                # Runtime state
                "status":               "UNKNOWN",
                "confidence_score":     0.0,
                "attempts":             0,
                "successful_attempts":  0,
                "last_visited":         None,
                "mode_scores":          {"socratic": 0.0, "feynman": 0.0, "devil_advocate": 0.0},
                "is_locked":            True,
                "is_prerequisite":      c.get("importance") == "critique",
                "is_leaf":              False,
                "flagged_for_review":   False,
            })

        # ── Step 2: Add PREREQUISITE_OF edges (sparse, not all-to-all) ───────
        # Each intermediate connects to at most 2 nearest fundamentals,
        # each advanced to at most 2 nearest intermediates.
        # This prevents the spaghetti star topology.
        def _sparse_prereqs(sources: list, targets: list, max_per_target: int = 2):
            if not sources or not targets:
                return
            for t_idx, t in enumerate(targets):
                if not self.graph.has_node(t):
                    continue
                # Connect to the `max_per_target` sources closest in index
                step = max(1, len(sources) // max_per_target)
                chosen = sources[t_idx % len(sources) : t_idx % len(sources) + max_per_target]
                if not chosen:
                    chosen = sources[:max_per_target]
                for s in chosen:
                    if self.graph.has_node(s) and s != t:
                        self.graph.add_edge(s, t,
                            edge_type="PREREQUISITE_OF", weight=1.0, constraint="HARD")

        _sparse_prereqs(fundamentals, intermediates, max_per_target=2)
        _sparse_prereqs(intermediates, advanced_list, max_per_target=2)

        # Also add RELATED_TO edges within the same tier for sibling concepts
        def _sibling_edges(tier: list, max_links: int = 1):
            for i, a in enumerate(tier):
                for b in tier[i+1:i+1+max_links]:
                    if self.graph.has_node(a) and self.graph.has_node(b):
                        self.graph.add_edge(a, b, edge_type="RELATED_TO", weight=0.5)

        _sibling_edges(fundamentals,  max_links=1)
        _sibling_edges(intermediates, max_links=1)
        _sibling_edges(advanced_list, max_links=1)


        # ── Step 3: Pre-seed known MisconceptionNodes ─────────────────────────
        for c in concepts_json.get("essential_concepts", []):
            for m_text in c.get("common_misconceptions", []):
                m_id = f"misc_{c['concept_id']}_{uuid.uuid4().hex[:6]}"
                self.graph.add_node(m_id, **{
                    "_type":            "misconception",
                    "misconception_id": m_id,
                    "parent_concept_id":c["concept_id"],
                    "wrong_statement":  m_text,
                    "correction":       "",
                    "detected_in_mode": None,
                    "detected_at":      None,
                    "resolved":         False,
                    "source":           "KNOWN",
                })
                self.graph.add_edge(c["concept_id"], m_id, edge_type="HAS_MISCONCEPTION")

        # ── Step 4: Unlock root nodes ─────────────────────────────────────────
        self._propagate_unlocks()
        self.save()
        return self.graph

    # ── format_for_react_force_graph ───────────────────────────────────────────
    # Direct equivalent of GraphBuilder.format_for_react_force_graph()

    def format_for_react_force_graph(self) -> Dict:
        """
        Serialise graph for the React frontend.
        Same format as the blockchain formatter:
          {
            "nodes": [{"id": "...", "group": ..., ...}],
            "links": [{"source": "...", "target": "...", "value": ..., ...}]
          }
        group = 0 UNKNOWN | 1 VISITED | 2 CONFUSED | 3 UNDERSTOOD | 4 MASTERED
        """
        status_group = {"UNKNOWN": 0, "VISITED": 1, "CONFUSED": 2, "UNDERSTOOD": 3, "MASTERED": 4}

        nodes = []
        for nid, data in self.graph.nodes(data=True):
            if data.get("_type") != "concept":
                continue
            nodes.append({
                "id":               nid,
                "group":            status_group.get(data.get("status", "UNKNOWN"), 0),
                "label":            data.get("name", nid),
                "bloom_level":      data.get("bloom_level"),
                "bloom_reached":    data.get("bloom_reached"),
                "confidence_score": round(data.get("confidence_score", 0.0), 4),
                "is_locked":        data.get("is_locked", True),
                "hierarchy_level":  data.get("hierarchy_level", "intermediate"),
                "status":           data.get("status", "UNKNOWN"),
            })

        active_confused_with = {
            (u, v)
            for u, v, d in self.graph.edges(data=True)
            if d.get("edge_type") == "CONFUSED_WITH"
        }

        links = []
        for u, v, data in self.graph.edges(data=True):
            et = data.get("edge_type", "")
            if et not in ("PREREQUISITE_OF", "RELATED_TO", "CONFUSED_WITH"):
                continue
            links.append({
                "source":           u,
                "target":           v,
                "value":            data.get("weight", 1.0),
                "edge_type":        et,
                "is_confused_with": (u, v) in active_confused_with,
            })

        return {"nodes": nodes, "links": links}

    # ── get_graph_stats ────────────────────────────────────────────────────────
    # Direct equivalent of GraphBuilder.get_graph_stats()

    def get_graph_stats(self) -> Dict:
        """Returns NetworkX statistics — same method as blockchain GraphBuilder."""
        g = self.graph
        concept_nodes = [n for n, d in g.nodes(data=True) if d.get("_type") == "concept"]
        mastered = sum(
            1 for n in concept_nodes
            if g.nodes[n].get("status") == "MASTERED"
        )
        return {
            "num_nodes":    g.number_of_nodes(),
            "num_concepts": len(concept_nodes),
            "num_edges":    g.number_of_edges(),
            "is_connected": (
                nx.is_weakly_connected(g) if g.number_of_nodes() > 0 else False
            ),
            "density":      nx.density(g),
            "mastered":     mastered,
            "progress_pct": round(mastered / len(concept_nodes) * 100, 1) if concept_nodes else 0.0,
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def concept_node_ids(self) -> List[str]:
        return [n for n, d in self.graph.nodes(data=True) if d.get("_type") == "concept"]

    def get_concept(self, concept_id: str) -> Optional[Dict]:
        if self.graph.has_node(concept_id):
            return dict(self.graph.nodes[concept_id])
        return None

    def _hard_prereqs(self, node_id: str) -> List[str]:
        return [
            p for p in self.graph.predecessors(node_id)
            if self.graph.edges[p, node_id].get("edge_type") == "PREREQUISITE_OF"
            and self.graph.edges[p, node_id].get("constraint") == "HARD"
        ]

    def get_active_misconceptions(self, concept_id: str) -> List[Dict]:
        result = []
        for n in self.graph.successors(concept_id):
            d = self.graph.nodes[n]
            if d.get("_type") == "misconception" and not d.get("resolved"):
                result.append(dict(d))
        return result

    def get_recommended_mode(self, concept_id: str) -> str:
        node = self.graph.nodes.get(concept_id, {})
        if self.get_active_misconceptions(concept_id):
            return "devil_advocate"
        br  = node.get("bloom_reached", "remember")
        idx = BLOOM_ORDER.index(br) if br in BLOOM_ORDER else 0
        if idx <= 1: return "feynman"
        if idx <= 3: return "socratic"
        return "devil_advocate"

    def get_next_concept(self) -> Optional[str]:
        for status in ("CONFUSED", "VISITED", "UNKNOWN"):
            for cid in self.concept_node_ids():
                n = self.graph.nodes[cid]
                if n.get("status") == status and not n.get("is_locked", True):
                    return cid
        return None

    # ── Update after student response ─────────────────────────────────────────

    def update_concept(
        self,
        concept_id: str,
        score: float,
        bloom_achieved: str,
        misconceptions_detected: List[str],
        mode: str,
    ):
        if not self.graph.has_node(concept_id):
            return
        node = self.graph.nodes[concept_id]
        node["attempts"]     = node.get("attempts", 0) + 1
        node["last_visited"] = datetime.utcnow().isoformat()

        # EMA confidence (same weighting as in the blockchain analyzer)
        old = node.get("confidence_score", 0.0)
        node["confidence_score"] = round(0.65 * old + 0.35 * score, 4)

        # Bloom — only go up
        if bloom_achieved in BLOOM_ORDER:
            cur_idx = BLOOM_ORDER.index(node.get("bloom_reached", "remember"))
            ach_idx = BLOOM_ORDER.index(bloom_achieved)
            if ach_idx > cur_idx:
                node["bloom_reached"] = bloom_achieved

        # Mode score EMA
        ms = node.get("mode_scores", {"socratic": 0.0, "feynman": 0.0, "devil_advocate": 0.0})
        ms[mode] = round(0.65 * ms.get(mode, 0.0) + 0.35 * score, 4)
        node["mode_scores"] = ms

        # Status thresholds
        if   score < 0.30: node["status"] = "CONFUSED";    node["flagged_for_review"] = True
        elif score < 0.55: node["status"] = "VISITED"
        elif score < 0.85:
            node["status"] = "UNDERSTOOD"
            node["successful_attempts"] = node.get("successful_attempts", 0) + 1
        else:
            node["status"] = "MASTERED"
            node["successful_attempts"] = node.get("successful_attempts", 0) + 1
            node["flagged_for_review"]  = False

        for m_text in misconceptions_detected:
            self._add_misconception(concept_id, m_text, mode)

        self._propagate_unlocks()
        self.save()

    def _add_misconception(self, concept_id: str, wrong_statement: str, mode: str):
        m_id = f"misc_{concept_id}_{uuid.uuid4().hex[:6]}"
        self.graph.add_node(m_id, **{
            "_type":            "misconception",
            "misconception_id": m_id,
            "parent_concept_id":concept_id,
            "wrong_statement":  wrong_statement,
            "correction":       "",
            "detected_in_mode": mode,
            "detected_at":      datetime.utcnow().isoformat(),
            "resolved":         False,
            "source":           "DETECTED",
        })
        self.graph.add_edge(concept_id, m_id, edge_type="HAS_MISCONCEPTION")

    def _propagate_unlocks(self):
        for nid in self.concept_node_ids():
            prereqs = self._hard_prereqs(nid)
            if not prereqs:
                self.graph.nodes[nid]["is_locked"] = False
            else:
                all_met = all(
                    self.graph.nodes[p].get("status") in ("UNDERSTOOD", "MASTERED")
                    for p in prereqs
                )
                self.graph.nodes[nid]["is_locked"] = not all_met

    # ── Session management ─────────────────────────────────────────────────────

    def start_session(self) -> str:
        sid = str(uuid.uuid4())
        self._sessions.append({
            "session_id":         sid,
            "started_at":         datetime.utcnow().isoformat(),
            "ended_at":           None,
            "mode_sequence":      [],
            "concepts_visited":   [],
            "misconceptions_found":[],
            "overall_score":      0.0,
        })
        self.save()
        return sid

    def end_session(self, session_id: str) -> dict:
        for s in self._sessions:
            if s["session_id"] == session_id:
                s["ended_at"] = datetime.utcnow().isoformat()
                self.save()
                return s
        return {}

    # ── Frontend serialisation (legacy — keep for backward compat) ─────────────

    def get_state(self) -> Dict:
        """
        Returns the full graph state for the React LucidityGraph component.
        Uses format_for_react_force_graph() internally for the node/link arrays.
        """
        fg = self.format_for_react_force_graph()

        # Also expose raw concept list (used by LucidityGraph's layered layout)
        concepts, misconceptions = [], []
        for nid, data in self.graph.nodes(data=True):
            t = data.get("_type")
            if t == "concept":
                concepts.append({k: v for k, v in data.items()})
            elif t == "misconception" and not data.get("resolved"):
                misconceptions.append({k: v for k, v in data.items()})

        edges = fg["links"]   # already filtered to PREREQUISITE_OF / RELATED_TO / CONFUSED_WITH

        return {
            # LucidityGraph uses these:
            "concepts":              concepts,
            "edges":                 edges,
            "active_misconceptions": misconceptions,
            "sessions":              self._sessions,
            # Force-graph extras:
            "force_graph":           fg,
            "stats":                 self.get_graph_stats(),
        }


# ── Back-compat alias (callers that still use KnowledgeGraph or get_graph()) ──
KnowledgeGraph = GraphBuilder


# ── Global registry ────────────────────────────────────────────────────────────
_registry: Dict[str, GraphBuilder] = {}


def get_graph(notebook_id: str) -> GraphBuilder:
    if notebook_id not in _registry:
        _registry[notebook_id] = GraphBuilder(notebook_id)
    return _registry[notebook_id]
