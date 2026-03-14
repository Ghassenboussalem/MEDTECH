"""
graph_storage.py — MAÏEUTICA Graph Storage
Adapted from GraphStorage (blockchain project).

Optionally persists the knowledge graph to Neo4j or Memgraph for rich
graph-database queries and external visualisation tools (Bloom, Perspective).

Usage:
    from graph_storage import GraphStorage
    storage = GraphStorage(storage_type="neo4j")   # or "memgraph"
    result  = storage.save_graph(graph_builder, notebook_id)

Neo4j schema:
    (:Concept  {concept_id, name, status, bloom_level, bloom_reached, ...})
    (:Misconception {misconception_id, wrong_statement, resolved, ...})
    (:Session  {session_id, started_at, ended_at, overall_score})
    (:Notebook {notebook_id})

    (:Concept)-[:PREREQUISITE_OF]->(:Concept)
    (:Concept)-[:RELATED_TO]->(:Concept)
    (:Concept)-[:CONFUSED_WITH]->(:Concept)
    (:Concept)-[:HAS_MISCONCEPTION]->(:Misconception)
    (:Concept)-[:VISITED_IN]->(:Session)
"""
from typing import Dict, Optional
import networkx as nx

# Local import — works without graph module loaded
try:
    from graph import GraphBuilder
except ImportError:
    GraphBuilder = None  # type: ignore


class GraphStorage:
    """
    Saves the MAÏEUTICA knowledge graph to a graph database.
    Optionally called — JSON persistence in graph.py is the primary store.

    Same interface as the blockchain GraphStorage:
        __init__(storage_type)
        save_graph(graph_builder, notebook_id)
    """

    def __init__(self, storage_type: str = "neo4j"):
        """
        Args:
            storage_type: "neo4j" or "memgraph"
        """
        self.storage_type = storage_type.lower()
        self.driver = None

    def save_graph(self, graph_builder: "GraphBuilder", notebook_id: str) -> Dict:
        """
        Persist the knowledge graph to the database.
        Returns a dict with success flag and stats — same contract as blockchain version.
        """
        if self.storage_type == "neo4j":
            return self._save_to_neo4j(graph_builder, notebook_id)
        elif self.storage_type == "memgraph":
            return self._save_to_memgraph(graph_builder, notebook_id)
        else:
            raise ValueError(
                f"Storage type '{self.storage_type}' not supported. Use 'neo4j' or 'memgraph'."
            )

    # ── Neo4j ──────────────────────────────────────────────────────────────────

    def _save_to_neo4j(self, graph_builder: "GraphBuilder", notebook_id: str) -> Dict:
        """Save concept graph to Neo4j — adapted from blockchain _save_to_neo4j."""
        try:
            from neo4j import GraphDatabase

            uri      = _env("NEO4J_URI",      "bolt://localhost:7687")
            user     = _env("NEO4J_USER",     "neo4j")
            password = _env("NEO4J_PASSWORD", "neo4j")

            print(f"  💾 Connecting to Neo4j at {uri}…")
            driver = GraphDatabase.driver(uri, auth=(user, password))
            driver.verify_connectivity()

            g: nx.DiGraph = graph_builder.graph

            with driver.session() as session:
                # Constraints
                _try_run(session, """
                    CREATE CONSTRAINT concept_id IF NOT EXISTS
                    FOR (c:Concept) REQUIRE c.concept_id IS UNIQUE
                """)
                _try_run(session, """
                    CREATE CONSTRAINT notebook_id IF NOT EXISTS
                    FOR (nb:Notebook) REQUIRE nb.notebook_id IS UNIQUE
                """)

                # Notebook node
                session.run("""
                    MERGE (nb:Notebook {notebook_id: $id})
                """, id=notebook_id)

                # ── Concept nodes (batch) ─────────────────────────────────
                # Same UNWIND batch pattern as blockchain GraphBuilder
                batch_size = 500
                concept_nodes = [
                    (nid, data) for nid, data in g.nodes(data=True)
                    if data.get("_type") == "concept"
                ]
                concepts_upserted = 0

                for i in range(0, len(concept_nodes), batch_size):
                    batch = concept_nodes[i:i + batch_size]
                    payload = [
                        {
                            "concept_id":       nid,
                            "name":             d.get("name", nid),
                            "description":      d.get("description", ""),
                            "importance":       d.get("importance", "importante"),
                            "bloom_level":      d.get("bloom_level", "understand"),
                            "bloom_reached":    d.get("bloom_reached", "remember"),
                            "hierarchy_level":  d.get("hierarchy_level", "intermediate"),
                            "status":           d.get("status", "UNKNOWN"),
                            "confidence_score": float(d.get("confidence_score", 0.0)),
                            "attempts":         int(d.get("attempts", 0)),
                            "is_locked":        bool(d.get("is_locked", True)),
                            "flagged_for_review":bool(d.get("flagged_for_review", False)),
                        }
                        for nid, d in batch
                    ]
                    result = session.run("""
                        UNWIND $nodes AS c
                        MERGE (n:Concept {concept_id: c.concept_id})
                        ON CREATE SET n += c
                        ON MATCH  SET
                            n.status           = c.status,
                            n.confidence_score = c.confidence_score,
                            n.bloom_reached    = c.bloom_reached,
                            n.attempts         = c.attempts,
                            n.is_locked        = c.is_locked,
                            n.flagged_for_review = c.flagged_for_review
                        RETURN count(n) AS count
                    """, nodes=payload)
                    concepts_upserted += result.single()["count"]

                # ── Misconception nodes ───────────────────────────────────
                misc_nodes = [
                    (nid, data) for nid, data in g.nodes(data=True)
                    if data.get("_type") == "misconception"
                ]
                for nid, d in misc_nodes:
                    session.run("""
                        MERGE (m:Misconception {misconception_id: $id})
                        ON CREATE SET
                            m.wrong_statement  = $wrong,
                            m.correction       = $correction,
                            m.source           = $source,
                            m.resolved         = $resolved,
                            m.detected_at      = $detected_at,
                            m.detected_in_mode = $mode
                        ON MATCH SET
                            m.resolved    = $resolved,
                            m.correction  = $correction
                    """,
                        id=nid,
                        wrong=d.get("wrong_statement", ""),
                        correction=d.get("correction", ""),
                        source=d.get("source", "DETECTED"),
                        resolved=bool(d.get("resolved", False)),
                        detected_at=d.get("detected_at"),
                        mode=d.get("detected_in_mode"),
                    )

                # ── Edges (batch) ─────────────────────────────────────────
                # Same UNWIND pattern as blockchain for TRANSFERRED relationships
                all_edges = list(g.edges(data=True))
                relationships_created = 0

                for i in range(0, len(all_edges), batch_size):
                    batch = all_edges[i:i + batch_size]
                    for u, v, data in batch:
                        et = data.get("edge_type", "")
                        if et == "PREREQUISITE_OF":
                            r = session.run("""
                                MATCH (a {concept_id: $u})
                                MATCH (b {concept_id: $v})
                                MERGE (a)-[r:PREREQUISITE_OF]->(b)
                                RETURN count(r) AS c
                            """, u=u, v=v)
                        elif et == "RELATED_TO":
                            r = session.run("""
                                MATCH (a {concept_id: $u})
                                MATCH (b {concept_id: $v})
                                MERGE (a)-[r:RELATED_TO]->(b)
                                RETURN count(r) AS c
                            """, u=u, v=v)
                        elif et == "CONFUSED_WITH":
                            r = session.run("""
                                MATCH (a {concept_id: $u})
                                MATCH (b {concept_id: $v})
                                MERGE (a)-[r:CONFUSED_WITH]->(b)
                                RETURN count(r) AS c
                            """, u=u, v=v)
                        elif et == "HAS_MISCONCEPTION":
                            r = session.run("""
                                MATCH (a {concept_id: $u})
                                MATCH (m:Misconception {misconception_id: $v})
                                MERGE (a)-[r:HAS_MISCONCEPTION]->(m)
                                RETURN count(r) AS c
                            """, u=u, v=v)
                        else:
                            continue
                        relationships_created += r.single()["c"]

                # Link Notebook → Concepts
                session.run("""
                    MATCH (nb:Notebook {notebook_id: $notebook_id})
                    MATCH (c:Concept)
                    MERGE (nb)-[:HAS_CONCEPT]->(c)
                """, notebook_id=notebook_id)

                stats = session.run("""
                    MATCH (c:Concept) WITH count(c) AS concepts
                    MATCH ()-[r]->() RETURN concepts, count(r) AS rels
                """).single()

            driver.close()

            return {
                "success":                True,
                "storage_type":           "neo4j",
                "concepts_upserted":      concepts_upserted,
                "relationships_created":  relationships_created,
                "total_concepts":         stats["concepts"],
                "total_relationships":    stats["rels"],
                "uri":                    uri,
            }

        except ImportError:
            return {"success": False, "error": "Neo4j driver not installed. Run: pip install neo4j"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Memgraph ───────────────────────────────────────────────────────────────

    def _save_to_memgraph(self, graph_builder: "GraphBuilder", notebook_id: str) -> Dict:
        """
        Save to Memgraph.
        Memgraph uses the same Bolt protocol + Neo4j driver — same Cypher, faster writes.
        Adapted from blockchain _save_to_memgraph.
        """
        try:
            from neo4j import GraphDatabase

            uri      = _env("MEMGRAPH_URI",      "bolt://localhost:7687")
            user     = _env("MEMGRAPH_USER",     "")
            password = _env("MEMGRAPH_PASSWORD", "")

            print(f"  💾 Connecting to Memgraph at {uri}…")
            if user or password:
                driver = GraphDatabase.driver(uri, auth=(user, password))
            else:
                driver = GraphDatabase.driver(uri)
            driver.verify_connectivity()

            g: nx.DiGraph = graph_builder.graph

            with driver.session() as session:
                # Memgraph constraint syntax
                _try_run(session, "CREATE CONSTRAINT ON (c:Concept) ASSERT c.concept_id IS UNIQUE")
                _try_run(session, "CREATE CONSTRAINT ON (nb:Notebook) ASSERT nb.notebook_id IS UNIQUE")

                session.run("MERGE (nb:Notebook {notebook_id: $id})", id=notebook_id)

                # Concept nodes (individual MERGE — Memgraph UNWIND can be slower for large batches)
                concept_nodes = [
                    (nid, data) for nid, data in g.nodes(data=True)
                    if data.get("_type") == "concept"
                ]
                batch_size = 100
                for i in range(0, len(concept_nodes), batch_size):
                    batch = concept_nodes[i:i + batch_size]
                    for nid, d in batch:
                        session.run("""
                            MERGE (c:Concept {concept_id: $cid})
                            ON CREATE SET
                                c.name              = $name,
                                c.description       = $description,
                                c.bloom_level       = $bloom_level,
                                c.hierarchy_level   = $hierarchy_level
                            ON MATCH SET
                                c.status            = $status,
                                c.bloom_reached     = $bloom_reached,
                                c.confidence_score  = $confidence_score,
                                c.is_locked         = $is_locked,
                                c.attempts          = $attempts
                        """,
                            cid=nid,
                            name=d.get("name", nid),
                            description=d.get("description", ""),
                            bloom_level=d.get("bloom_level", "understand"),
                            hierarchy_level=d.get("hierarchy_level", "intermediate"),
                            status=d.get("status", "UNKNOWN"),
                            bloom_reached=d.get("bloom_reached", "remember"),
                            confidence_score=float(d.get("confidence_score", 0.0)),
                            is_locked=bool(d.get("is_locked", True)),
                            attempts=int(d.get("attempts", 0)),
                        )

                # Edges
                for u, v, data in g.edges(data=True):
                    et = data.get("edge_type", "")
                    if et == "PREREQUISITE_OF":
                        session.run("""
                            MATCH (a:Concept {concept_id: $u})
                            MATCH (b:Concept {concept_id: $v})
                            MERGE (a)-[:PREREQUISITE_OF]->(b)
                        """, u=u, v=v)
                    elif et == "RELATED_TO":
                        session.run("""
                            MATCH (a:Concept {concept_id: $u})
                            MATCH (b:Concept {concept_id: $v})
                            MERGE (a)-[:RELATED_TO]->(b)
                        """, u=u, v=v)
                    elif et == "CONFUSED_WITH":
                        session.run("""
                            MATCH (a:Concept {concept_id: $u})
                            MATCH (b:Concept {concept_id: $v})
                            MERGE (a)-[:CONFUSED_WITH]->(b)
                        """, u=u, v=v)
                    elif et == "HAS_MISCONCEPTION":
                        session.run("""
                            MATCH (a:Concept {concept_id: $u})
                            MATCH (m:Misconception {misconception_id: $v})
                            MERGE (a)-[:HAS_MISCONCEPTION]->(m)
                        """, u=u, v=v)

                session.run("""
                    MATCH (nb:Notebook {notebook_id: $id})
                    MATCH (c:Concept)
                    MERGE (nb)-[:HAS_CONCEPT]->(c)
                """, id=notebook_id)

                stats = session.run("""
                    MATCH (c:Concept) WITH count(c) AS concepts
                    MATCH ()-[r]->() RETURN concepts, count(r) AS rels
                """).single()

            driver.close()

            return {
                "success":             True,
                "storage_type":        "memgraph",
                "total_concepts":      stats["concepts"],
                "total_relationships": stats["rels"],
                "uri":                 uri,
            }

        except ImportError:
            return {"success": False, "error": "Neo4j driver not installed. Run: pip install neo4j"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _env(key: str, default: str) -> str:
    """Read config from environment or .env file, fallback to default."""
    import os
    return os.environ.get(key, default)


def _try_run(session, cypher: str):
    """Run a Cypher statement, silently ignore errors (e.g. constraint already exists)."""
    try:
        session.run(cypher)
    except Exception:
        pass
