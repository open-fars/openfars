# OpenFARS

[English](README.md) | [简体中文](README_CN.md)

**一个本地优先、面向非平庸创意的多智能体科研操作系统。**

OpenFARS 为每个研究阶段选择最合适的模型，搜索兼具质量与多样性的创意前沿，只在高价值
决策点请求人类参与，在本地或远程 GPU 上运行真实实验，并将经过验证的证据转化为图表、
论文、媒体制作包和可审查的开放科学发布包。

```text
方向 → 文献 → 探索 → 批判 → 任务 → 计划
     → 实验 ⇄ 评估 → 图表 → 论文 → 播客 → 视频 → 发布
```

## 有何不同

- **不是 Best-of-N 头脑风暴：** 使用因果发散算子、异构模型家族、最近邻文献检查、
  盲审裁判和质量多样性档案。
- **Human Gradient，有限上下文：** 决策包只展示入围方案、证伪条件、异常与分歧，
  而不是完整对话记录。
- **内置 DeepSeek Harness：** 实验 Agent 使用持久 Harness 会话，并支持插件组合、
  沙箱工具、生命周期事件和工作区权限。
- **真实科研基础设施：** 支持 SSH GPU 执行、仅追加轨迹、失败实验保留、确定性绘图和
  证据锁定引用。
- **本地 WebUI：** 展示实时 Agent 流水线、SSE 事件流、研究产物与人工审批；密钥不会
  进入浏览器。
- **安全的一键开源：** 生成校验和、项目卡、RO-Crate，并在验证身份后显式发布至
  GitHub、Hugging Face 和 ModelScope。

## 快速开始

需要 Python 3.10+。

```bash
git clone https://github.com/open-fars/openfars.git
cd openfars
pip install -e .

# 无需密钥的演示：完成整个工作流，但绝不会伪造实验依据。
openfars web --config examples/offline.yaml
```

如需使用前沿模型路由：

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

密钥只从环境变量读取，切勿将 Token 写入 YAML。OpenFARS 通过 LiteLLM 统一适配器支持
100 多种托管或本地模型服务，同时允许每个 Agent 独立选择模型。Ark、OpenRouter、vLLM
和 Ollama 等示例见[模型服务配置](docs/PROVIDERS.md)。

## 默认模型团队

默认配置是截至 **2026-08-15**、基于现有证据的快照，并不代表永久排名。

| 角色 | 默认模型 |
|---|---|
| director、librarian、task_designer、critic、evaluator | GPT‑5.6 Sol |
| explorer | Claude Opus 4.8 + GPT/Gemini/DeepSeek 模型池 |
| planner、writer、podcaster | Claude Opus 4.8 |
| experimenter | 通过 DeepSeek Harness 使用 DeepSeek‑V4‑Pro |
| visualizer | GPT‑5.6 Sol + 确定性渲染器 |
| video_producer | Gemini 3.6 Flash |
| publisher | GPT‑5.6 Luna + 确定性权限检查 |

13 个角色的当前最佳设计、备选模型和晋级基准详见
[docs/AGENTS.md](docs/AGENTS.md)。可通过以下命令刷新按任务分类的排行榜快照：

```bash
openfars models-refresh --config openfars.local.yaml --force
```

排行榜快照仅提供建议，绝不会静默改写模型路由。WebUI 会在后台刷新过期订阅；只使用
CLI 的用户可显式运行上述命令。

播客与视频 Agent 始终生成证据关联且可由人类审查的源文件制作包。如需同时渲染最终
二进制文件，可使用 `{package}`、`{output}` 和 `{workspace}` 占位符配置无 Shell 的
参数列表：

```yaml
media:
  podcast_render_command: [python, tools/render_podcast.py, --input, "{package}", --output, "{output}"]
  video_render_command: [node, tools/render_video.mjs, --storyboard, "{package}", --output, "{output}"]
```

渲染器的标准输出和错误输出只保存在不会发布的会话日志中；发布包仅包含二进制文件、
校验和及脱敏后的渲染回执。

## 远程 GPU 实验

私钥始终保留在控制端机器上，并通过环境变量引用其路径：

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

OpenFARS 调用系统的 `ssh`/`rsync`，不会读取或上传私钥内容。参见
[examples/remote-gpu.example.yaml](examples/remote-gpu.example.yaml)。每次执行前会清除旧的
远程结果契约，执行后再将新结果拉回；远程结果优先于控制端草稿，失败命令绝不能产生
“继续推进”的结论。远程命令会收到 `OPENFARS_REMOTE_OUTPUT_DIR`、
`OPENFARS_DATASETS_DIR`、`OPENFARS_MODELS_DIR`、`OPENFARS_PROJECT_ID` 和
`OPENFARS_ITERATION`。检查点及大型产物应写入输出目录，而不是同步的代码工作区。

Harness 默认使用 fail-closed 的 `workspace-write` 权限，需要可用的 bubblewrap/Landlock
（Linux）或 sandbox-exec（macOS）后端。只有在已经隔离、可随时销毁的环境中，才应在
对应模型路由上显式设置 `permission_mode: danger-full-access`；OpenFARS 永不自动降级。

## 运行、审查与发布

```bash
openfars run --config openfars.local.yaml --topic "你的大致研究方向"
openfars status <project-id> --config openfars.local.yaml
openfars decide <project-id> idea --approve --select <idea-id> --feedback "..."
# 也可以修改整个创意前沿；历史候选项与反馈会被完整归档。
openfars decide <project-id> idea --revise --feedback "寻找成本更低的因果证伪实验"

# 只生成本地发布包，不执行外部写入。
openfars bundle <project-id> --config openfars.local.yaml

# 显式授权外部发布；发布前会验证登录身份。
openfars publish <project-id> --github --confirm --config openfars.local.yaml
```

GitHub 发布仅允许已认证账号 `Dingrui-Wang`；仓库所有者为 `open-fars`。每个外部发布
目标都必须获得用户显式提供的权限。

## 设计文档

- [架构与 DeepSeek Harness 映射](docs/ARCHITECTURE.md)
- [Agent 调研与模型路由](docs/AGENTS.md)
- [模型与 API 服务商](docs/PROVIDERS.md)
- [Auto-research 缺口、OpenClaw 启示与产品论述](docs/PRODUCT_THESIS.md)

```bash
pip install -e '.[dev]'
pytest
ruff check src tests scripts run.py
# 安装 Harness extra 后运行；只使用本机回环的模拟服务商。
python scripts/harness_smoke.py
```

本项目采用 MIT 许可证。AI 生成的研究产物必须披露 AI 协助，并始终接受人类对科学性、
安全性、隐私和许可证的审查。
