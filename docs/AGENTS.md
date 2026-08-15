# Agent design and model routing

Snapshot: **2026-08-15**. “Best” here means the strongest default for OpenFARS' role contract,
not a permanent universal ranking. Public leaderboards are a prior; route promotion requires a
version-pinned shadow evaluation on OpenFARS tasks, including quality, failure rate, latency,
cost, tool use, and cognitive correlation with the other agents.

## Default matrix

| Agent | Best current design | Default controller model | Independent challenger / renderer | Promotion signal |
|---|---|---|---|---|
| `director` | Orchestrator that creates a bounded charter, budget, success definition, and high-value human decision frontier | `gpt-5.6-sol` at max reasoning | `claude-opus-4-8` | Agents' Last Exam + OpenFARS direction pairwise review |
| `librarian` | Iterative query expansion → metadata/full-text retrieval → reranking → contextual summaries → evidence/contradiction graph | `gpt-5.6-sol` | Gemini Deep Research / Asta Paper Finder | DeepResearch Bench, LiveResearchBench, Asta PaperFindingBench, citation precision |
| `explorer` | Operator-conditioned quality-diversity search with a novelty archive; never IID “brainstorm N times” | `claude-opus-4-8` | pool: GPT‑5.6 Sol, Gemini 3.6 Flash, DeepSeek‑V4‑Pro | downstream experimental value, archive coverage, external novelty—not self-rated novelty |
| `critic` | Blind, independent heterogeneous judgments; preserve disagreement and fatal flaws instead of debate consensus | `gpt-5.6-sol` at max reasoning | `gemini-3.6-flash` auxiliary reviewer | calibration, false-advance rate, judge disagreement and bias tests |
| `task_designer` | Turn one hypothesis into variables, controls, minimum useful effect, executable decision rule, and informative failures | `gpt-5.6-sol` at max reasoning | `claude-opus-4-8` | expert rubric coverage + executable-contract pass rate |
| `planner` | Preregister cheapest decisive pilot, baselines, seeds, confounders, stop rules, and environment capture | `claude-opus-4-8` | `gpt-5.6-sol` | PaperBench rubric coverage + preregistration audit |
| `experimenter` | Durable inspect→edit→smoke-test→run→debug loop; sandboxed tools, append-only events, persistent session, remote GPU | `deepseek-v4-pro` through DeepSeek Harness | `gpt-5.6-sol` coding shadow route | Terminal‑Bench, SWE‑bench, PaperBench and project-local executable tests |
| `evaluator` | Apply executable preregistered rule first; model explains residual ambiguity; output `advance/iterate/stop` | `gpt-5.6-sol` at max reasoning | `gemini-3.6-flash` | false-positive advance rate, calibration, reproducibility and blinded expert agreement |
| `visualizer` | Semantic chart intent → data-linked declarative spec → deterministic render → visual/claim audit | `gpt-5.6-sol` | Gemini 3.6 Flash; deterministic SVG/Vega-Lite renderer | chart reasoning, data fidelity, accessibility and claim support |
| `writer` | Evidence-locked drafting with immutable citation IDs and claim-level audit | `claude-opus-4-8` | `gpt-5.6-sol` | factuality, citation entailment, expert readability; never style-only preference |
| `podcaster` | Evidence-linked multi-speaker script → consent-safe TTS → ASR round-trip factual audit → disclosure | `claude-opus-4-8` | FireRedTTS2 renderer | script factuality, speaker consistency, pronunciation, TTS arena and ASR agreement |
| `video_producer` | Claim-linked storyboard → programmatic charts/diagrams → optional generated inserts → frame/transcript audit | `gemini-3.6-flash` | Gemini Omni Flash / Remotion + ffmpeg | evidence fidelity, temporal consistency, legibility and video arena |
| `publisher` | Build checksummed RO-Crate first; verify identity/namespace/license; external writes require explicit approval | `gpt-5.6-luna` | deterministic adapters are authoritative | dry-run contract, identity mismatch rejection, checksum and reproducibility validation |

`reviewer` is an auxiliary, source-blind judge routed to Gemini 3.6 Flash. It is deliberately
separate from the user-facing `critic` so a single model family cannot both generate and ratify
an idea.

## Why each design

### `director`

Use an orchestrator-worker control plane, but keep artifacts—not the director's chat history—as
the source of truth. The charter contains scope, non-goals, budget and an explicit definition of
success. Human attention is requested only where expected value of information is high.
Anthropic's production research system reports the same lead-agent/specialist pattern, while
DeepSeek Harness supplies the stronger lifecycle primitive: replaceable plugins and durable
events rather than a monolithic prompt.

Sources: [Anthropic multi-agent research architecture](https://www.anthropic.com/engineering/multi-agent-research-system),
[DeepSeek Harness architecture](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md).

### `librarian`

Static top-k RAG is insufficient. The librarian expands and revises queries, retains source
provenance, distinguishes abstract-only evidence from full text, builds a contradiction graph,
and hands later agents stable evidence IDs. PaperQA2 is the strongest open pattern to borrow;
AstaBench is used to prevent retrieval quality from being confused with general model fluency.

Sources: [PaperQA2](https://github.com/Future-House/paper-qa),
[AstaBench](https://allenai.org/asta/bench),
[DeepResearch Bench](https://arxiv.org/abs/2506.11763).

### `explorer`

Next-token training does not literally compute a numeric mean, but ordinary decoding favors
high-density continuations. Repeating the same context/model therefore produces correlated,
conventional variations. OpenFARS samples **causal operators** (inversion, mechanism transfer,
measurement attack, bottleneck removal), rotates heterogeneous model families, deduplicates,
checks nearest literature, and keeps the best idea per behavior/resource cell. The archive
rewards both quality and coverage, following MAP-Elites rather than best-of-N voting.

Sources: [MAP-Elites / quality diversity](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2016.00040/full),
[AI Scientist v2 tree search](https://github.com/SakanaAI/AI-Scientist-v2).

### `critic`

Candidate author, operator and source model are hidden. Multiple model families judge
independently; OpenFARS records the median and the spread, but does not let agents debate until
they converge. Debate can amplify a shared bias, while heterogeneous agents can expose it.
Fatal confounders and cheap falsifiers are carried into the human packet.

Sources: [multi-agent debate bias study](https://arxiv.org/abs/2608.02827),
[AstaBench evaluation principles](https://allenai.org/blog/astabench).

### `task_designer`

The task is a contract, not a topic: independent/dependent variables, controls, exclusion
criteria, minimum useful effect, budget, and an executable decision rule. A negative result must
be informative. This is separate from planning so a planner cannot quietly redefine the claim
to fit an easy experiment.

Sources: [OSF preregistration guidance](https://help.osf.io/article/330-welcome-to-registrations),
[PaperBench's author-built hierarchical rubrics](https://openai.com/index/paperbench/).

### `planner`

The plan fixes baselines, seeds, metrics, confounders, resource limits and stop conditions before
the first expensive run. It starts with a cheap instrumentation pilot and records the environment.
Changes after observing results remain visible as iterations; they never overwrite the original
preregistration.

Sources: [Karpathy autoresearch protocol](https://github.com/karpathy/autoresearch/blob/master/program.md),
[OSF registrations](https://help.osf.io/article/330-welcome-to-registrations).

### `experimenter`

This role uses DeepSeek Harness as a real long-running agent harness, not an HTTP wrapper:
durable same-agent sessions, sandboxed Bash, workspace permissions, tool/step events, and a
Cordis composition. Each iteration preserves code, logs, failures, metrics and checkpoints.
Remote SSH receives a local key **path**, never key bytes; code sync excludes credentials.

Sources: [DeepSeek Harness Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/python-sdk.md),
[DeepSeek Harness providers](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md),
[PaperBench](https://github.com/openai/frontier-evals/tree/main/project/paperbench),
[Terminal-Bench](https://www.tbench.ai/leaderboard/terminal-bench/2.0).

### `evaluator`

An executable decision object has precedence over model opinion. Otherwise a model reviews the
preregistered task, plan, observed metrics and full failure history, then emits only
`advance`, `iterate`, or `stop`. Iteration changes one requested variable; max iterations and
resource stop conditions remain hard bounds.

Sources: [PaperBench reproducible execution and grading](https://openai.com/index/paperbench/),
[AstaBench E2E evaluation](https://allenai.org/asta/bench).

### `visualizer`

The LLM proposes semantic intent and captions, not pixels that may invent data. Numeric artifacts
drive a deterministic SVG/Vega-Lite renderer. A later audit checks axes, omitted failures,
uncertainty, accessibility and whether each visual claim is supported.

Sources: [Vega-Lite grammar](https://vis.mit.edu/pubs/vega-lite/),
[Google PaperVizAgent](https://research.google/blog/improving-the-academic-workflow-introducing-two-ai-agents-for-better-figures-and-peer-review/).

### `writer`

The paper reads only verified project artifacts and an immutable evidence ledger. It can cite
`[P1]`, not invent bibliographic strings. The audit rejects unknown IDs and preserves failed or
skipped experiments as such. This avoids the observed tendency for forced citation generation to
increase hallucinated references.

Source: [citation accuracy under constrained generation](https://proceedings.mlr.press/v318/davis26a.html).

### `podcaster`

The controller writes an evidence-linked script and disclosure. A separate TTS renderer produces
consent-safe voices; voice cloning or imitation requires explicit rights. The rendered audio is
transcribed back and compared with the script before release. FireRedTTS2 is the current open
default because it targets long, multilingual, multi-speaker dialogue.

Source: [FireRedTTS2](https://github.com/FireRedTeam/FireRedTTS2).

### `video_producer`

The agent creates a source-linked storyboard. Charts and diagrams are programmatic and
reproducible; generated video is optional and labeled. The pipeline samples rendered frames,
checks text legibility and compares narration against the evidence ledger. It must never fabricate
lab footage as experimental evidence.

Sources: [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models),
[Remotion](https://github.com/remotion-dev/remotion).

### `publisher`

Publication is deterministic and permissioned. The agent first builds cards, checksums, a ZIP and
RO-Crate metadata locally. GitHub calls verify the authenticated login is exactly
`Dingrui-Wang`; the repository owner remains `open-fars`. Hugging Face and ModelScope verify the
authenticated namespace. Every destination requires `--confirm`; no research run can publish.

Sources: [RO-Crate](https://www.researchobject.org/ro-crate/),
[GitHub authenticated user API](https://docs.github.com/en/rest/users/users#get-the-authenticated-user),
[Hugging Face upload guide](https://huggingface.co/docs/huggingface_hub/guides/upload),
[ModelScope Hub](https://github.com/modelscope/modelscope_hub).

## Model evidence and refresh policy

The initial routing uses current public model IDs and official capability reports:

- GPT‑5.6 Sol is the flagship default for complex reasoning/coding and exposes a 1.05M context
  window; OpenFARS uses it for the hardest control and evaluation contracts.
  [Official model guide](https://developers.openai.com/api/docs/models).
- Claude Opus 4.8 is Anthropic's long-running coding/agent/professional-work model; OpenFARS uses
  its different model family for planning, exploration and prose.
  [Official announcement](https://www.anthropic.com/news/claude-opus-4-8).
- Gemini 3.6 Flash is a stable, fast agentic/multimodal model with a 1M context window; it supplies
  an independent judge and media-aware route.
  [Official model guide](https://ai.google.dev/gemini-api/docs/latest-model).
- DeepSeek‑V4‑Pro is the open-weight 1M-context agentic model used inside DeepSeek Harness.
  [Official release](https://api-docs.deepseek.com/news/news260424/).

Run `openfars models-refresh --force` to cache the configured feeds. The subscriber covers
Artificial Analysis, SWE-bench, Terminal-Bench, PaperBench, DeepResearch Bench,
LiveResearchBench, and media arenas. It writes an advisory report under
`outputs/_model_registry/leaderboards/`; it never edits `openfars.yaml`. Starting the WebUI
refreshes a stale snapshot in the background and exposes only route names, model IDs and feed
status to the browser—never credentials.
