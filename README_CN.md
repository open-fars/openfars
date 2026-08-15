# OpenFARS

[English](README.md) | [简体中文](README_CN.md)

**让不同的模型各做自己擅长的事，把一个研究想法一路推进到实验、论文和开源发布。**

OpenFARS 是一套本地优先的多智能体科研系统。它不假设某个模型能够包打天下：查文献、
想点子、写代码、看实验、画图和写论文可以分别交给不同的模型，整个过程则由一条可暂停、
可追溯的工作流串起来。

```text
确定方向 → 查文献 → 找突破口 → 挑错 → 定任务 → 做计划
        → 跑实验 ⇄ 看结果 → 画图 → 写论文 → 播客 → 视频 → 开源发布
```

## 为什么做 OpenFARS

科研最怕“看起来都对，但没有新东西”。

大模型擅长给出稳妥、常见的答案。多采样几次通常只是得到更多相似答案，不一定更接近一个
真正值得做的想法。OpenFARS 因此没有把重点放在生成更多，而是放在三件事上：

- **把想法拉开。** 用因果扰动、跨模型探索、最近文献比对和盲审，把候选想法放进一个
  同时考虑质量与差异性的候选池。
- **让人只管关键判断。** 系统在选方向、定想法、看异常和发布前停下来，把少量真正需要
  判断的信息交给人，而不是让人翻几十页 Agent 对话。
- **让实验说话。** 结论必须能追到代码、日志、指标和引用。失败的实验不会被藏起来，
  也不会被包装成“有希望的结果”。

在这条主线之外，OpenFARS 还提供：

- 13 个分工明确的 Agent，每个 Agent 都能单独换模型；
- 基于 DeepSeek Harness 的持久实验会话、工具调用和权限控制；
- 本地 WebUI，可看进度、审产物、改想法、批准或驳回下一步；
- 本地与 SSH 远程 GPU 实验；
- 论文、图表、播客和视频制作；
- 带校验和、项目卡和 RO-Crate 的开源发布包。

密钥只留在运行 OpenFARS 的机器上，不会进入浏览器。

## 先跑起来

需要 Python 3.10+。

```bash
git clone https://github.com/open-fars/openfars.git
cd openfars
pip install -e .

# 不需要任何 API Key。它会走完整流程，但不会伪造实验结果。
openfars web --config examples/offline.yaml
```

如果要接入真实模型：

```bash
pip install -e '.[models,harness,publish]'
cp openfars.yaml openfars.local.yaml

export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...
export DEEPSEEK_API_KEY=...

openfars doctor --config openfars.local.yaml
openfars web --config openfars.local.yaml
```

不要把 Token 写进 YAML。OpenFARS 通过 LiteLLM 接入 100 多种云端和本地模型，同时保留
每个 Agent 独立选模型的能力。Ark、OpenRouter、vLLM、Ollama 等配置示例见
[模型服务配置](docs/PROVIDERS.md)。

## 默认模型怎么分工

下面是 **2026-08-15** 的默认阵容。它只是当前快照，不是永久榜单。

| 工作 | 默认模型 |
|---|---|
| 把关方向、查文献、设计任务、批判与评估 | GPT‑5.6 Sol |
| 探索想法 | Claude Opus 4.8 + GPT/Gemini/DeepSeek 混合模型池 |
| 做计划、写论文、写播客 | Claude Opus 4.8 |
| 写代码、跑实验 | DeepSeek‑V4‑Pro + DeepSeek Harness |
| 画图 | GPT‑5.6 Sol + 确定性渲染器 |
| 做视频 | Gemini 3.6 Flash |
| 整理并发布 | GPT‑5.6 Luna + 确定性权限检查 |

为什么这样搭配、各角色还有哪些备选模型，以及新模型达到什么标准才能替换默认模型，都写在
[Agent 与模型路由](docs/AGENTS.md)里。

模型排行会变，可以手动刷新：

```bash
openfars models-refresh --config openfars.local.yaml --force
```

WebUI 也会在后台刷新过期榜单。这些榜单只给建议，不会偷偷改掉现有路由。

## 远程跑 GPU 实验

SSH 私钥留在控制端，只在配置中写保存私钥路径的环境变量名：

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

OpenFARS 调用系统自带的 `ssh` 和 `rsync`，不会读取或上传私钥内容。完整例子见
[远程 GPU 配置](examples/remote-gpu.example.yaml)。

每次实验开始前，旧的远程结果文件会先被清掉；命令结束后，新结果再拉回本地。远程命令失败，
评估器就不能给出“继续推进”。检查点和大文件应写进 `output_dir`，不要塞进同步的代码目录。

Harness 默认使用 fail-closed 的 `workspace-write` 权限，需要 Linux 上可用的
bubblewrap/Landlock，或 macOS 上的 sandbox-exec。只有运行环境本身已经隔离且随时可以
销毁时，才应显式使用 `permission_mode: danger-full-access`；OpenFARS 不会自动放宽权限。

## 从想法走到发布

```bash
openfars run --config openfars.local.yaml --topic "你的研究方向"
openfars status <project-id> --config openfars.local.yaml

# 认可其中一个想法
openfars decide <project-id> idea --approve --select <idea-id> --feedback "..."

# 或者告诉系统哪里不对，让它重新找；旧候选和反馈都会保留
openfars decide <project-id> idea --revise --feedback "找一个成本更低的因果证伪实验"

# 只在本地生成发布包，不会上传
openfars bundle <project-id> --config openfars.local.yaml

# 明确确认后才会发布；发布前还会核对登录身份
openfars publish <project-id> --github --confirm --config openfars.local.yaml
```

GitHub 发布只允许已认证的 `Dingrui-Wang` 账号，目标仓库属于 `open-fars`。GitHub、
Hugging Face 和 ModelScope 都需要用户自己提供权限，OpenFARS 不会替用户默认开启发布。

## 播客与视频

默认情况下，播客和视频 Agent 会先产出带证据链接、可以人工修改的制作包。要直接渲染
WAV 或 MP4，可以配置参数数组：

```yaml
media:
  podcast_render_command: [python, tools/render_podcast.py, --input, "{package}", --output, "{output}"]
  video_render_command: [node, tools/render_video.mjs, --storyboard, "{package}", --output, "{output}"]
```

支持 `{package}`、`{output}` 和 `{workspace}` 三个占位符。渲染日志留在本地会话目录，
发布包只收录成品、校验和与脱敏后的渲染记录。

## 想看实现细节

- [整体架构与 DeepSeek Harness 的对应关系](docs/ARCHITECTURE.md)
- [13 个 Agent 的设计与模型选择](docs/AGENTS.md)
- [模型与 API 服务商配置](docs/PROVIDERS.md)
- [现有 Auto-research 的问题、OpenClaw 的启发与产品思路](docs/PRODUCT_THESIS.md)

```bash
pip install -e '.[dev]'
pytest
ruff check src tests scripts run.py

# 需要安装 harness extra；测试只访问本机的模拟服务
python scripts/harness_smoke.py
```

OpenFARS 使用 MIT 许可证。由 AI 参与生成的研究成果应说明 AI 的参与方式，并由人类继续
负责科学性、安全、隐私与许可证审查。
