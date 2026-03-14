# Lucidity Graph Generation & Node Architecture

This document explains how the **MAÏEUTICA Knowledge Graph** (frontend name: Lucidity Graph) is dynamically generated from raw texts and how its nodes, layers, and states are structured.

---

## 🧠 1. The Generation Workflow (Backend Pass)

The graph generation relies on a **Two-Pass LLM Pipeline** orchestrated by `concept_extractor.py`. When a user clicks "Build Knowledge Graph," the backend fetches all vector embeddings for that notebook and passes them to the local `llama3.2` model.

### Pass 1: Concept Extraction (`extract_concepts`)
The LLM is prompted to act as an "expert educational content analyst." It reads the document context and extracts the core concepts into a rigid JSON structure:
- **`concept_id`**: A unique snake_case identifier.
- **`name`** & **`description`**: Human-readable title and summary.
- **`importance`**: `critique` (must master), `importante` (should master), `utile` (nice to know).
- **`bloom_level`**: The *target* cognitive level for this concept (e.g., `understand`, `apply`, `analyze`).
- **`concept_hierarchy`**: The LLM automatically bins each extracted concept into one of three layers:
  - `fundamental`: Concepts requiring no prior knowledge.
  - `intermediate`: Concepts requiring fundamental knowledge.
  - `advanced`: Concepts requiring intermediate knowledge.

### Pass 2: Course Structural Design (`extract_course_structure`)
The LLM is then prompted as a "curriculum designer." It takes the raw text + the list of concepts extracted in Pass 1 to build a cohesive learning path:
- Groups concepts into logical **Modules**.
- Determines **Learning Outcomes**.
- Defines teaching and assessment strategies (e.g., Feynman technique, worked examples).

### Graph Building (`graph.py`)
Once the JSON is extracted, the `GraphBuilder` class (using the `NetworkX` library) constructs a Directed Graph (`DiGraph`):
1. **Node Creation**: Every concept becomes a node (initialized with `0.0` confidence, `UNKNOWN` status, and `is_locked = True` for non-fundamentals).
2. **Edge Creation**: Hard-coded prerequisite edges (`PREREQUISITE_OF`) are drawn between the hierarchy layers: `fundamental` → `intermediate` → `advanced`.
3. **Misconception Seeding**: Socratic "Misconception" nodes are pre-attached to concepts based on common misunderstandings identified by the LLM in Pass 1.
4. **Unlocking**: The graph runs `_propagate_unlocks()` to unlock the `fundamental` root nodes so the student can start learning.

---

## 🕸️ 2. Frontend Visualization (Lucidity Graph)

The `LucidityGraph.jsx` component uses `react-force-graph-2d` to render the data payload from the backend. The layers defined in Pass 1 dictate the physical layout of the graph on the canvas.

### Layered Architecture (DAG Layout)
The graph uses a Directed Acyclic Graph (DAG) layout engine (`dagMode="td"` for Top-Down).
- **Layer 0 (Top)**: `fundamental` concepts.
- **Layer 1 (Middle)**: `intermediate` concepts.
- **Layer 2 (Bottom)**: `advanced` concepts.

Because the backend explicitly created `PREREQUISITE_OF` edges cascading down these layers, the physics engine naturally organizes the nodes hierarchically without overlapping clusters.

---

## 🚦 3. Node State & Bloom's Taxonomy Mastery

Nodes in the MAÏEUTICA graph are stateful. As the student converses with the Socratic AI, the backend scores their responses and updates the node's state.

### Node Status Flow
A node's visual color and icon change based on its `status`:
1. 🔒 **LOCKED** (Gray): Prerequisites have not been mastered yet.
2. ❓ **UNKNOWN** (Light Blue): Fully unlocked, ready to be learned, but unattempted.
3. 👣 **VISITED** (Blue): Attempted, but score is low (< 55%).
4. ⚠️ **CONFUSED** (Orange/Red): Score is very low (< 30%). The node is flagged for review, and a `HAS_MISCONCEPTION` edge may be dynamically generated.
5. 🧠 **UNDERSTOOD** (Purple): Score > 55%. Prerequisites for child nodes are unlocked.
6. 👑 **MASTERED** (Gold): Score > 85% + Target Bloom's Level achieved.

### Dynamic Edge Generation
While `PREREQUISITE_OF` edges are static (created at generation), the graph also supports dynamic cognitive edges:
- `CONFUSED_WITH`: If the AI detects the student mixing up two concepts during chat, the backend draws a link between them.
- `HAS_MISCONCEPTION`: Links a concept to a tracked misunderstanding that must be resolved (usually triggering the "Devil's Advocate" AI mode).
