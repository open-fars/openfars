# Product thesis

## Where current auto-research systems fall short

- Many optimize one editable file against one fixed metric. That loop is powerful for a narrow
  benchmark but has no literature, task selection, human judgment, multimodel diversity or
  publication semantics. [Karpathy autoresearch](https://github.com/karpathy/autoresearch).
- End-to-end paper agents add idea generation and tree search, but success is still fragile,
  generated code is risky, and fluency can conceal missing evidence.
  [AI Scientist v2](https://github.com/SakanaAI/AI-Scientist-v2).
- Deep-research systems are far better at reports than at discovery. Hard broad/deep literature
  tasks and end-to-end scientific execution remain weak; tools, corpus, cost and model capability
  are often confounded. [DeepResearch Bench](https://arxiv.org/abs/2506.11763),
  [AstaBench](https://allenai.org/blog/astabench),
  [PaperBench](https://openai.com/index/paperbench/).
- “Generate many and vote” spends more inference but stays inside one model/context distribution.
  Self-evaluated novelty and debate consensus are especially unreliable.

## Why OpenClaw became a breakout product

OpenClaw made agents tangible: local-first ownership, fast onboarding, existing communication
channels, a persistent gateway, broad model/provider choice, tools/skills/plugins, and a memorable
identity. Users see actions, not an architecture diagram. Its rapid adoption is therefore a
product lesson as much as a model lesson. [OpenClaw](https://github.com/openclaw/openclaw),
[official site](https://openclaw.ai/).

## OpenFARS' wedge

OpenFARS should be the **research OS that gets from a risky question to reviewable evidence and a
shareable artifact**.

1. **Ideas beyond the mode.** Search different causal transformations with heterogeneous model
   families; maintain a quality-diversity archive; use external literature and experiments rather
   than model confidence to validate novelty.
2. **Human gradients, not human transcript reading.** Ask about frontier choices, anomalies,
   evaluator disagreement and high-value information. Store feedback as an immutable decision and
   route it only to affected downstream stages. A `revise` decision resamples the heterogeneous
   idea frontier under that gradient while retaining the previous frontier for audit.
3. **Real work.** Literature retrieval, durable code agents, SSH GPU execution, bounded failure
   iteration, deterministic charts, evidence-locked papers, media packages and reproducible
   release objects live in one workflow.
4. **A visible control plane.** The WebUI makes agents, events, decisions and artifacts legible in
   real time. A zero-key offline demo completes in seconds without pretending it ran science.
5. **Trustworthy openness.** Credentials stay local, failed results remain evidence, publication
   is separately authorized, and every release is checksummed with provenance.

The moat is not another prompt chain. It is the accumulated evaluation data connecting
idea-search operators, agent/model routes, human decisions, experiment outcomes and publication
quality across real research projects.
