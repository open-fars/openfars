# OpenFARS

[English](README.md) | [简体中文](README_CN.md)

**一套本地优先的多智能体科研系统，用来寻找不落俗套的研究思路。**

OpenFARS 会为每个研究阶段选择最合适的模型，探索既有质量、又有差异的想法，只在真正需要
人做判断时停下来提问，在本地或远程 GPU 上运行真实实验，最后把可靠的证据整理成图表、
论文、音视频制作包和一套可供审查的开放科学发布包。

```text
研究方向 → 文献调研 → 思路探索 → 批判 → 任务设计 → 实验计划
         → 实验 ⇄ 评估 → 图表 → 论文 → 播客 → 视频 → 发布
```

## 它有什么不同

- **不只是 Best-of-N 头脑风暴：** 通过因果变换主动拉开思路，让不同模型参与探索，再结合
  相近文献检查、盲审和质量多样性档案来筛选想法。
- **由人校准方向，但不让人淹没在上下文里：** 决策包只展示入围方案、可能推翻结论的证据、
  异常和分歧，而不是整段对话记录。
- **内置 DeepSeek Harness：** 实验 Agent 使用可持续工作的 Harness 会话，并支持插件组合、
  沙箱工具、生命周期事件和工作区权限。
- **接入真实科研环境：** 支持通过 SSH 使用 GPU、保留只追加不覆盖的运行记录、记录失败实验、
  生成可复现的图表，并确保引用都有证据支撑。
- **本地 WebUI：** 可以实时查看 Agent 流程、SSE 事件、研究产物和人工审批；密钥不会进入
  浏览器。
- **安全的一键开源：** 生成校验和、项目卡和 RO-Crate，并在明确授权、验证身份后发布到
  GitHub、Hugging Face 和 ModelScope。

## 快速开始

需要 Python 3.10 或更高版本。

```bash
git clone https://github.com/open-fars/openfars.git
cd openfars
pip install -e .

# 不需要 API Key。它会走完整个流程，但不会假装产生了实验结果。
openfars web --config examples/offline.yaml
```

如果要使用前沿模型：

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

密钥只从环境变量读取，不要把 Token 写进 YAML。OpenFARS 通过 LiteLLM 的统一接口支持
100 多种云端和本地模型，同时允许每个 Agent 独立选择模型。Ark、OpenRouter、vLLM 和
Ollama 的配置示例见[模型服务配置](docs/PROVIDERS.md)。

## 默认模型组合

下面的默认配置是截至 **2026-08-15**、根据现有证据做出的选择，并不代表这些模型会一直领先。

| Agent | 默认模型 |
|---|---|
| director、librarian、task_designer、critic、evaluator | GPT‑5.6 Sol |
| explorer | Claude Opus 4.8 + GPT/Gemini/DeepSeek 模型池 |
| planner、writer、podcaster | Claude Opus 4.8 |
| experimenter | 通过 DeepSeek Harness 使用 DeepSeek‑V4‑Pro |
| visualizer | GPT‑5.6 Sol + 确定性渲染器 |
| video_producer | Gemini 3.6 Flash |
| publisher | GPT‑5.6 Luna + 确定性权限检查 |

13 个 Agent 的详细设计、其他可选模型和模型晋级标准都在
[docs/AGENTS.md](docs/AGENTS.md)中。可以用下面的命令刷新各项任务的排行榜快照：

```bash
openfars models-refresh --config openfars.local.yaml --force
```

这些快照只提供参考，不会在背后自动修改模型路由。WebUI 会在后台刷新已经过期的订阅；
只使用命令行时，也可以手动运行上面的命令。

播客和视频 Agent 始终会先生成带有证据链接、可以由人审核的制作包。如果还需要渲染最终
文件，可以用 `{package}`、`{output}` 和 `{workspace}` 占位符配置参数列表，
不需要拼接 Shell 命令：

```yaml
media:
  podcast_render_command: [python, tools/render_podcast.py, --input, "{package}", --output, "{output}"]
  video_render_command: [node, tools/render_video.mjs, --storyboard, "{package}", --output, "{output}"]
```

渲染器的标准输出和错误输出只保存在不会发布的会话日志里；发布包只包含最终文件、校验和
以及脱敏后的渲染记录。

## 远程 GPU 实验

私钥保留在控制端机器上，配置文件只通过环境变量引用它的路径：

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

OpenFARS 调用系统自带的 `ssh` 和 `rsync`，不会读取或上传私钥内容。配置示例见
[examples/remote-gpu.example.yaml](examples/remote-gpu.example.yaml)。

每次执行前，旧的远程结果文件都会先被清除；命令结束后，新结果会拉回本地，并优先于控制端
生成的草稿。只要命令执行失败，系统就不会给出“继续推进”的结论。远程命令可以读取
`OPENFARS_REMOTE_OUTPUT_DIR`、`OPENFARS_DATASETS_DIR`、`OPENFARS_MODELS_DIR`、
`OPENFARS_PROJECT_ID` 和 `OPENFARS_ITERATION`。检查点和大型文件应保存在输出目录，
不要放进同步的代码工作区。

Harness 默认采用 fail-closed 的 `workspace-write` 权限，因此需要 Linux 上可用的
bubblewrap/Landlock，或 macOS 上的 sandbox-exec。只有环境本身已经隔离、并且用完即可
销毁时，才应在对应的模型路由中明确设置 `permission_mode: danger-full-access`；
OpenFARS 不会自动降低安全限制。

## 运行、审核和发布

```bash
openfars run --config openfars.local.yaml --topic "你的研究方向"
openfars status <project-id> --config openfars.local.yaml
openfars decide <project-id> idea --approve --select <idea-id> --feedback "..."
# 也可以要求系统重新探索整个候选集；之前的候选和反馈都会保留。
openfars decide <project-id> idea --revise --feedback "寻找成本更低的因果证伪实验"

# 只生成本地发布包，不会写入任何外部平台。
openfars bundle <project-id> --config openfars.local.yaml

# 明确授权后才会对外发布；发布前会先验证登录身份。
openfars publish <project-id> --github --confirm --config openfars.local.yaml
```

GitHub 发布只允许已认证的 `Dingrui-Wang` 账号，仓库所有者为 `open-fars`。发布到任何
外部平台，都需要用户明确提供相应权限。

## 设计文档

- [整体架构与 DeepSeek Harness 的对应关系](docs/ARCHITECTURE.md)
- [Agent 调研与模型路由](docs/AGENTS.md)
- [模型与 API 服务商](docs/PROVIDERS.md)
- [Auto-research 的不足、OpenClaw 的启发和产品思路](docs/PRODUCT_THESIS.md)

```bash
pip install -e '.[dev]'
pytest
ruff check src tests scripts run.py
# 需要安装 Harness extra；测试只会使用本机回环的模拟服务。
python scripts/harness_smoke.py
```

本项目采用 MIT 许可证。由 AI 参与生成的研究成果需要说明 AI 的参与方式，并继续由人审核
其科学性、安全性、隐私和许可证合规性。
