# Lucidity Nodes: Structure, Reinforcement, and Multi-Method Tutoring

This document explains how Lucidity nodes are built, unlocked, assessed, and reinforced.

## 1. Node Generation Model

Lucidity graph nodes are generated from notebook sources using a multi-agent pipeline:

- Structure extraction agent
- Quiz generation agent
- Graph layout agent
- Content/tutor agents for remediation

## 1.1 Multi-Agent Architecture

Lucidity uses a cooperative multi-agent design where each agent has a strict responsibility.

Agents and responsibilities:

- `PDFExtractorAgent`
  - Extracts raw text from PDF sources.
  - Produces normalized source documents `{filename, text, page_count}`.

- `StructureAgent`
  - Builds the conceptual tree (chapters, sections, subsections).
  - Produces semantic summaries used by downstream quiz/content generation.

- `QuizAgent`
  - Generates 3 node-specific MCQs for every node.
  - Enforces quality constraints (non-generic stems, plausible distractors, node grounding).

- `GraphLayoutAgent`
  - Converts the conceptual tree into renderable Lucidity nodes with coordinates and edges.
  - Applies initial unlock policy (root + first chapter unlocked).

- `ContentAgent`
  - Generates rich on-demand explanatory content when the learner opens a node.
  - Structures explanations to support remediation and review.

- `TutorAgent`
  - Runs interactive tutoring in one of 3 methods (`feynman`, `socratic`, `devil`).
  - Used after failed quiz outcomes to reinforce understanding.

- `OrchestratorAgent`
  - Coordinates the full pipeline and updates progress state.
  - Handles asynchronous session lifecycle and final graph payload publishing.

Control flow (simplified):

1. Sources are collected (text docs + optional image descriptions).
2. `OrchestratorAgent` triggers extraction and structure synthesis.
3. `QuizAgent` enriches each node with assessments.
4. `GraphLayoutAgent` builds final node/edge graph JSON.
5. Frontend polls session status and loads graph when ready.
6. During learning, `ContentAgent` and `TutorAgent` run on-demand per node.

This separation improves scalability and maintainability:

- Each agent can evolve independently.
- Failures are isolated to a specific stage.
- New agent capabilities can be inserted without rewriting the whole pipeline.

Node payload typically includes:

- `id`
- `type` (`root`, `chapter`, `section`, `sub`)
- `summary`
- `quiz` (3 MCQs)
- `connections`
- `unlocked`
- `mastered`

## 2. Unlock Policy

Default unlock behavior:

- Root node is unlocked.
- First chapter node is also unlocked by default to ensure immediate progression.
- Other nodes unlock through progression after mastering prerequisites.

Reset behavior:

- Root remains unlocked.
- First chapter remains unlocked.
- Other nodes return to locked state.

## 3. Quiz Quality Policy

Quiz generation enforces node specificity:

- Exactly 3 questions per node.
- Questions target different cognitive intents:
  - factual
  - mechanism/relationship
  - application/diagnosis
- Generic stems are rejected.
- Distractors must be plausible, not joke/random options.
- Validation checks that question/choices are grounded in node title/summary keywords.

## 4. Multi-Method Tutoring

When learners fail quiz questions, Lucidity uses three pedagogical methods:

- `feynman`: simplify and rebuild understanding
- `socratic`: guided questioning
- `devil`: challenge misconceptions and force justification

These methods are not static; they are selected adaptively.

## 5. Reinforcement Mechanism

Lucidity uses a lightweight online reinforcement strategy (bandit-style) per `(session_id, node_id)`:

- Method selection endpoint chooses next tutor mode.
- Feedback endpoint updates method rewards.
- Reward examples:
  - `1.0` when learner succeeds after tutoring
  - `0.0` when learner still fails after intervention

This drives personalization while staying computationally cheap and scalable.

## 6. Session Endpoints (Lucidity)

Key endpoints used by Lucidity frontend:

- `POST /api/from-notebook/{notebook_id}`
- `GET /api/status/{session_id}`
- `GET /api/graph/{session_id}`
- `POST /api/chat`
- `POST /api/node-content`
- `POST /api/tutor-method/select`
- `POST /api/tutor-method/feedback`

## 7. Image-Aware Learning Context

Notebook images uploaded in Sources are described via `llava:latest` and added to learning context.
This helps nodes and quizzes align with visual material (diagrams, charts, slides, screenshots).
