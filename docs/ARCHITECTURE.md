# Architecture

OpenFARS is a local-first research control plane. Models are replaceable workers; durable
artifacts, events and human decisions are the source of truth.

```text
WebUI / CLI
    │  same-origin JSON + SSE
    ▼
Research control plane ── human gates ── publisher permission boundary
    │
Plugin runtime ── lifecycle hooks ── injected services ── typed handoffs
    │
13 agent plugins ── multi-model router ── DeepSeek Harness session
    │
OpenAlex / local workspace / SSH GPU / release adapters
    │
events.jsonl + artifacts + handoffs + decisions + session logs
```

## What is borrowed deeply from DeepSeek Harness

OpenFARS follows the mechanisms described in the
[Harness architecture](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md),
not only its model API:

| Harness mechanism | OpenFARS implementation |
|---|---|
| Cordis “everything is a plugin” composition | Every research role implements `ResearchPlugin`; services and plugins can be replaced independently. |
| Scoped registrations and cleanup | Each plugin gets a `PluginScope`; unmount disposes its hooks and service entry. |
| Waterfall/interceptable events | `stage.before`, `stage.after`, and `stage.error` hooks can transform or refuse a stage input. |
| Durable session/event log | `events.jsonl` is append-only; state and UI are projections. DeepSeek Harness keeps its own experimenter session log under `sessions/`. |
| Typed turn/step/tool lifecycle | `StageResult`, `agent.lifecycle`, model request/response hashes, state transitions and typed handoffs. |
| Replaceable capability seams | Literature, idea search, experiment runner, evaluator, visualizer, media and release builder are injected services. |
| Persisted same-agent work | Experiment iterations reuse one Harness `session_id`, preserving tool context without copying the whole transcript. |
| Permission modes | The shipped Cordis profile uses `workspace-write`, sandboxed Bash and no bare editor; publication is a separate explicit effect boundary. |
| Browser client from event projection | The local WebUI consumes project/event APIs and SSE; it never owns research state. |
| Loopback-first Web server | `127.0.0.1` is enforced. Remote access must be placed behind an authenticated reverse proxy. |

The Web carrier is intentionally separate from the research loop. It serves static assets and a
domain API, while project projections are reconstructed from the durable store. Like Harness,
side-effecting requests must be same-origin `application/json`; simple cross-site form requests
are rejected. The browser never receives model credentials, W&B configuration or SSH key paths.

OpenFARS is smaller than Harness: it does not yet load arbitrary third-party browser bundles or
offer full bidirectional RPC. That boundary is deliberate until plugin signing, capability
declarations and authorization are designed.

## Workflow state machine

```text
director → librarian → explorer → critic → [human: idea]
  → task_designer → planner → [human: plan]
  → experimenter ⇄ evaluator (bounded iterations)
  → [human: results] → visualizer → writer
  → podcaster → video_producer → publisher(bundle only)
  → [human: publication] → complete
```

Every completed plugin writes a content-hashed handoff containing only its summary, produced
artifacts, evidence references, decisions and open questions. The receiving agent gets a bounded
context envelope; clipping never deletes the original artifact. This prevents full transcripts
from becoming an unbounded, unauditable pseudo-database.

## Idea search

OpenFARS does not ask one model to brainstorm repeatedly. The explorer rotates model families and
causal divergence operators. Candidates are deduplicated, checked against nearby literature,
blind-scored by heterogeneous judges, penalized for fatal flaws/disagreement, and stored in a
quality-diversity archive keyed by paradigm and resource profile. Human review sees the frontier,
falsifier, nearby evidence and judge spread—not the conversation.

## Experiment and remote compute boundary

The experimenter can use a local model route, DeepSeek Harness, and an SSH compute target. SSH is
executed by the system OpenSSH client with an argument vector. A configured identity file is only
referenced via `ssh -i`; its bytes are never read, serialized or synchronized. `rsync` excludes
keys, credentials and `.env` files. Remote relative paths are constrained below the configured
work directory.

Each iteration has its own result, agent response, stdout, stderr and evaluation. An executable
decision object beats LLM judgment. `iterate` carries one minimal next step into the same durable
experimenter session; max iterations and the preregistered stop conditions remain hard limits.

## Publication boundary

The publisher agent can only build a local release object. It produces cards, checksums,
RO-Crate metadata and an archive. The separate `openfars publish --confirm` command is the only
external path. It verifies authenticated identities and namespaces before GitHub, Hugging Face or
ModelScope writes.
