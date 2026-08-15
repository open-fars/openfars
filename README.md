# OpenFARS

[English](README.md) | [简体中文](README_CN.md)

**A local-first, multi-agent research OS for ideas beyond the average.**

OpenFARS routes each research stage to the model best suited to it, searches a
quality-diverse idea frontier, asks humans only for high-value decisions, runs real experiments
locally or on remote GPUs, and turns verified evidence into figures, a paper, media packages and
a reviewable open-science release.

```text
direction → literature → exploration → critique → task → plan
          → experiment ⇄ evaluation → figures → paper → podcast → video → release
```

## What is different

- **Not best-of-N brainstorming:** causal divergence operators, heterogeneous model families,
  nearest-literature checks, blind judges and a quality-diversity archive.
- **Human gradients, bounded context:** decision packets expose finalists, falsifiers, anomalies
  and disagreement—not full transcripts.
- **DeepSeek Harness inside:** the experimenter uses a durable Harness session with plugin
  composition, sandboxed tools, lifecycle events and workspace permissions.
- **Real research infrastructure:** SSH GPU execution, append-only traces, failed-run retention,
  deterministic plots and evidence-locked citations.
- **Local 3D WebUI:** a lightweight office shows all 13 agents walking, working and handing off
  tasks alongside the SSE event stream, artifacts and human approvals; secrets never enter the browser.
- **Safe one-click openness:** checksums, cards, RO-Crate and explicit, identity-verified publishing
  to GitHub, Hugging Face and ModelScope.

## Quickstart

Install Miniconda first. The commands below create an isolated Python 3.11 environment
(OpenFARS supports Python 3.10+).

```bash
conda create -n openfars python=3.11 -y
conda activate openfars

git clone https://github.com/open-fars/openfars.git
cd openfars
python -m pip install -e .

# Zero-key demo: completes the workflow but never simulates experimental evidence.
openfars web --config examples/offline.yaml
```

Open `http://127.0.0.1:8765`. The lightweight 3D office puts 13 clickable agents, the task graph,
live events and handoffs, artifacts, model routes and human decisions in one view. Appearance and
movement are adjustable; without WebGL, the same desks remain available in 2D.

For frontier routes:

```bash
python -m pip install -e '.[models,harness,publish]'
cp openfars.yaml openfars.local.yaml
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...
export DEEPSEEK_API_KEY=...
openfars doctor --config openfars.local.yaml
openfars web --config openfars.local.yaml
```

Keys are read from environment variables only. Never place tokens in YAML.
OpenFARS uses LiteLLM's unified adapter for 100+ hosted and local providers, while keeping model
choice independent per agent. See [provider configuration](docs/PROVIDERS.md), including Ark,
OpenRouter, vLLM and Ollama examples.

## Default model team

Defaults are an evidence-based snapshot dated **2026-08-15**, not permanent winners.

| Role | Default |
|---|---|
| director, librarian, task_designer, critic, evaluator | GPT‑5.6 Sol |
| explorer | Claude Opus 4.8 + GPT/Gemini/DeepSeek model pool |
| planner, writer, podcaster | Claude Opus 4.8 |
| experimenter | DeepSeek‑V4‑Pro through DeepSeek Harness |
| visualizer | GPT‑5.6 Sol + deterministic renderer |
| video_producer | Gemini 3.6 Flash |
| publisher | GPT‑5.6 Luna + deterministic permission checks |

The detailed current-best design, alternatives and promotion benchmarks for all 13 roles are in
[docs/AGENTS.md](docs/AGENTS.md). Refresh task-specific leaderboard snapshots with:

```bash
openfars models-refresh --config openfars.local.yaml --force
```

Snapshots are advisory and never silently rewrite model routes.
The WebUI refreshes stale subscriptions in the background; CLI-only users can run the command
above explicitly.

Podcast and video agents produce evidence-linked, reviewable source packages. Optional renderers
use shell-free argument lists; their logs stay out of the release bundle.

## Remote GPU experiments

Keep the private key on the controlling machine and reference its path through an environment
variable:

```yaml
compute:
  targets:
    gpu-lab:
      host: 121.89.85.xxx
      user: root
      port: 32430
      identity_file_env: OPENFARS_SSH_KEY
      workdir: /data/dingrui/code/openfars
      output_dir: /data/dingrui/output
      datasets_dir: /data/dingrui/datasets
      models_dir: /data/dingrui/models
```

```bash
export OPENFARS_SSH_KEY=/Users/xxx/.ssh/id_ed25519_xxx
openfars remote-probe gpu-lab --config openfars.local.yaml
```

OpenFARS calls system `ssh`/`rsync` without reading or uploading private-key bytes. It clears stale
remote results before each run and never advances after a failed command. See the
[remote GPU example](examples/remote-gpu.example.yaml) and [sandbox design](docs/ARCHITECTURE.md).

## Run, review, publish

```bash
openfars run --config openfars.local.yaml --topic "your broad direction"
openfars status <project-id> --config openfars.local.yaml
openfars decide <project-id> idea --approve --select <idea-id> --feedback "..."
# Or move the whole frontier; prior candidates and feedback remain archived.
openfars decide <project-id> idea --revise --feedback "seek a cheaper causal falsifier"

# Local bundle only; no external write.
openfars bundle <project-id> --config openfars.local.yaml

# Explicit external authorization; authenticated identities are verified first.
openfars publish <project-id> --github --confirm --config openfars.local.yaml
```

GitHub publication is restricted to authenticated account `Dingrui-Wang`; the repository owner is
`open-fars`. Every external destination requires explicit user-provided permission.

## Design

- [Architecture and DeepSeek Harness mapping](docs/ARCHITECTURE.md)
- [Agent research and model routing](docs/AGENTS.md)
- [Model/API providers](docs/PROVIDERS.md)
- [Auto-research gaps, OpenClaw lessons and product thesis](docs/PRODUCT_THESIS.md)

```bash
python -m pip install -e '.[dev]'
pytest
ruff check src tests scripts run.py
# With the Harness extra installed; uses only a loopback fake provider.
python scripts/harness_smoke.py
```

MIT licensed. AI-generated research artifacts must disclose AI assistance and remain subject to
human scientific, safety, privacy and license review.
