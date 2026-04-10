# afterglow-robot

一个面向**授权纪念用途**的本地私有化 AI Agent 方案：在用户自有 Windows PC 上，离线整理指定联系人的微信聊天记录、语音样本与表情使用习惯，构建文字风格拟合、语音克隆与私聊响应能力；核心数据处理与推理流程均以本地运行、数据不出机为前提设计。

> 当前仓库处于开源整理阶段。本文档优先定义目标架构、数据约定与接入方式，避免把尚未完成的能力表述成“已交付功能”。

## 合规与伦理说明

本项目仅建议用于以下场景：

- 本人对自己历史数据进行本地化整理与数字纪念；
- 经明确授权的家庭纪念、数字留念或研究用途；
- 在法律、平台规则与隐私约束允许范围内进行本地实验。

请勿将本项目用于以下用途：

- 未经授权的身份冒充、骚扰、欺诈或误导性交流；
- 未经同意的语音克隆、聊天风格复刻或隐私数据处理；
- 违反微信平台规则、当地法律法规或第三方协议的自动化接入。

如果你无法确认数据授权范围，请不要继续处理或分发相关数据。

## 项目定位

`afterglow-robot` 不是一个面向公网部署的通用人物克隆平台，而是一套强调**本地私有化、授权数据、纪念表达与可解释数据流**的 AI Agent 工作流。它将以下能力串联起来：

- **聊天风格拟合**：从历史对话中提炼 Few-shot 样本与语义检索库；
- **语音复现**：对微信语音样本做降噪、切分，并接入本地 TTS/声音克隆模型；
- **表情习惯还原**：结合语义相似度与历史使用频率检索表情包；
- **微信私聊接入**：通过 OpenClaw + 微信 ClawBot 官方插件接入个人微信私聊；
- **全链路本地运行**：核心数据处理、向量索引、LLM 推理与语音合成均以本机执行为主。

## 核心特性

- **全程本地优先**：聊天记录、数据库密钥、语音样本、向量库与模型权重默认保存在本机；
- **轻量风格方案**：基于 `Ollama + Qwen2.5-7B + RAG + Few-shot Prompt`，避免高成本 LoRA 微调；
- **可替换语音后端**：支持将 `GPT-SoVITS` 或 `CosyVoice2` 作为语音生成方案；
- **微信数据处理链完整**：覆盖 `wx_key`、`WeChatDataAnalysis`、SILK 解码、降噪与数据集构造；
- **多模态回复可扩展**：文本回复为核心能力，语音与表情回复按接入条件逐步完善。

## 系统架构总览

| 层级 | 职责 | 主要工具 |
| --- | --- | --- |
| 数据采集层 | 密钥提取、DB 解密、语音导出 | `wx_key`、`WeChatDataAnalysis` |
| 数据处理层 | 聊天记录解析、训练集构造、语音预处理 | `Python`、`silk-v3-decoder`、`ffmpeg`、`noisereduce` |
| 模型层 | 风格推理、声音克隆、表情检索 | `Ollama (Qwen2.5-7B)`、`GPT-SoVITS` / `CosyVoice2`、`CLIP` |
| Agent 调度层 | 消息路由、上下文管理、多模态决策 | `OpenClaw` + 自定义 `EchoSoul Skill` |
| 微信接入层 | 微信私聊收发 | 微信 `ClawBot` 官方插件（`iLink` 协议） |

## 数据流水线（一次性离线处理）

### 1. 密钥提取

- 使用 `wx_key.exe` 在目标 Windows 设备上，从运行中的微信 PC 进程中读取 `SQLCipher 4` 数据库解密密钥；
- 该密钥通常与设备环境绑定，建议仅在原始授权设备上执行一次；
- 提取结果可保存为 `data/db_key.txt`，后续解密流程离线进行，不再依赖微信进程持续运行。

### 2. 数据库解密与导出

- 使用 `WeChatDataAnalysis` 解密 `MSG*.db` 与 `MicroMsg.db`；
- 从 `WCContact` 表按微信号（`m_nsAliasName`）查询联系人，获取目标 `wxid`（`m_nsUsrName`）；
- 按目标 `wxid` 导出聊天记录、语音消息路径索引与表情资源路径列表；
- 文档中的默认导出路径示例为：

```text
C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output
```

> 说明：该路径是当前环境下常见默认值，不同机器、不同安装方式或不同版本的 `WeChatDataAnalysis` 可能有所差异，可以在配置中自行修改。

### 3. 语音预处理

微信语音通常为 `SILK v3` 格式，建议处理链如下：

```text
SILK v3
→ silk-v3-decoder
→ PCM
→ ffmpeg
→ WAV 16kHz mono
→ noisereduce
→ silero-vad
→ 3–30 秒音频片段
```

推荐目标：

- 最低可用语音样本：约 3 分钟；
- 明显提升效果：30 分钟以上；
- 微信原始语音压缩噪声较重，降噪与静音切分不建议省略。

### 4. 聊天记录处理与训练集构造

从导出数据中筛选目标 `wxid` 发出的消息，并与上一条上下文消息配对，构造 `(context, response)` 样本。建议过滤：

- 纯表情、纯图片与系统消息；
- 少于 4 个字的低信息量消息；
- 无法还原上下文的孤立消息。

建议产出两类数据：

- **风格样本集**：约 200–500 条精选 Q-A，用于 Few-shot Prompt；
- **完整话语向量库**：对全部有效消息做 embedding，写入 `ChromaDB`，供在线 RAG 检索使用。

### 5. 表情包向量化

- 扫描 `CustomEmotion` 目录；
- 使用 `CLIP`（如 `openai/clip-vit-base-patch32`）生成每张表情图片的语义向量；
- 结合聊天记录中的历史使用频率做权重排序；
- 推荐将元数据存入本地 `SQLite`，向量存为 `.npy` 文件。

### 6. 声音模型准备

可按硬件与可维护性选择两种路线：

- `GPT-SoVITS`：适合基于处理后的微信语音片段做 few-shot fine-tune；
- `CosyVoice2`：适合零样本或轻量参考音频克隆场景。

> 当前 README 仅定义接入方向，不把任何特定训练脚本描述为仓库内已实现能力。

## 在线推理链路

推荐的在线响应流程如下：

```text
收到微信私聊消息
→ OpenClaw 路由到 EchoSoul Skill
→ Ollama 生成风格化文本回复
→ 按情绪与频率判断是否附加表情
→ 如需表情：CLIP 检索候选表情
→ 如语音链路可用：调用 GPT-SoVITS / CosyVoice2 生成语音
→ 通过 ClawBot iLink 协议回传微信
```

上下文管理建议：

- 以“微信账号 + 聊天对象”作为独立会话键；
- 将最近对话窗口与长期记忆分开管理；
- 将 Few-shot 风格样本、RAG 检索结果与当前窗口消息组合后再交给 `Ollama`。

## 风格推理方案

本项目默认推荐**不做 LoRA 微调**，优先采用 `RAG + Few-shot Prompt`：

- 显存与训练成本更低，更适合 `RTX 3060 12G` 一类消费级显卡；
- 便于替换底层模型，不把风格拟合强绑定在某个专用权重上；
- 更符合本项目“本地、轻量、可维护”的目标。

推荐的 Prompt 组装方式：

```text
System Prompt（人物身份与说话约束）
+ Few-shot 样本（20 条左右）
+ RAG 检索结果（3–5 条相关历史对话）
+ 当前会话窗口（最近 10 轮）
+ 用户当前消息
```

System Prompt 约束建议：

- 用词、语气、标点尽量贴近历史样本；
- 回复长度参考真实对话，默认以短句为主；
- 不暴露 AI 身份，不解释内部推理过程；
- 对无法回答的内容优先保持克制，而不是编造记忆。

## 快速开始

> 下面是文档级接入步骤，用于说明系统如何搭建；并非表示仓库当前已提供所有自动化脚本。

### 1. 准备环境

建议环境：

- `Windows 10/11 64-bit`
- `Python 3.10+`
- NVIDIA GPU（最低 `RTX 3060 12G`，推荐 `RTX 4070 16G`）
- 最新版微信 PC 客户端
- 如需 ClawBot 私聊接入，建议同时具备受支持的微信移动端环境

### 2. 准备依赖工具

你需要自行安装并验证以下工具：

- `wx_key`
- `WeChatDataAnalysis`
- `silk-v3-decoder`
- `ffmpeg`
- `Ollama`
- `GPT-SoVITS` 或 `CosyVoice2`
- `OpenClaw`

安装当前仓库的 Python 依赖：

```bash
python -m pip install -e .
```

### 3. 导出微信数据

- 在授权设备上提取数据库密钥；
- 使用 `WeChatDataAnalysis` 解密并导出聊天记录；
- 确认目标联系人 `wxid`；
- 整理语音与表情资源目录。

默认导出目录通常类似：

```text
C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output
```

实际项目中建议将该路径写入配置文件，而不是在代码中写死。

### 4. 构造本地数据资产

需要至少准备以下几类资产：

- 聊天导出文件，例如 `data/chat_export.json`
- 原始语音文件目录，例如 `data/voice_raw/`
- 处理后语音片段目录，例如 `data/voice_processed/`
- 向量库目录，例如 `models/chroma_db/`
- 表情向量文件，例如 `models/emoji_vectors.npy`
- 语音模型权重目录，例如 `models/sovits_weights/`

### 4.1 先复制配置模板

建议先复制一份示例配置，再按你的账号与目标联系人填写：

```bash
Copy-Item "config.example.yaml" "config.yaml"
```

配置中至少需要确认以下字段：

- `wechat.export_dir`
- `wechat.account_wxid`
- `wechat.target_wxid`
- `output.base_dir`
- `embedding.chroma_dir`

### 4.2 运行第一阶段 3 个 CLI

当前仓库已经提供第一阶段离线文本管线的 3 个 CLI，建议按以下顺序执行。

**1）发现联系人**

如果导出目录下只有一个账号，可以直接扫描联系人并导出联系人清单：

```bash
python "process/discover_contacts.py" `
  --export-dir "C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output" `
  --output "data/outputs/contacts.json"
```

如果导出目录下存在多个账号，请额外传入 `--account-wxid`：

```bash
python "process/discover_contacts.py" `
  --export-dir "C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output" `
  --account-wxid "wxid_your_account" `
  --output "data/outputs/contacts.json"
```

**2）提取目标联系人聊天**

推荐方式是直接使用 `config.yaml`：

```bash
python "process/extract_chat.py" --config "config.yaml"
```

也可以显式传参运行：

```bash
python "process/extract_chat.py" `
  --export-dir "C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output" `
  --account-wxid "wxid_your_account" `
  --target-wxid "wxid_target_contact" `
  --output "data/outputs/wxid_target_contact/messages.normalized.jsonl"
```

**3）构建 Few-shot、RAG 与向量库**

同样推荐优先用配置文件驱动：

```bash
python "process/build_dataset.py" --config "config.yaml"
```

也可以显式传入输入与输出路径：

```bash
python "process/build_dataset.py" `
  --input "data/outputs/wxid_target_contact/messages.normalized.jsonl" `
  --output-dir "data/outputs/wxid_target_contact" `
  --chroma-dir "models/chroma_db"
```

执行完成后，第一阶段离线文本管线会产出：

- `data/outputs/contacts.json`
- `data/outputs/<target_wxid>/messages.normalized.jsonl`
- `data/outputs/<target_wxid>/fewshot.json`
- `data/outputs/<target_wxid>/rag_corpus.jsonl`
- `models/chroma_db/`

### 4.3 可选：一条命令跑完整个第一阶段

如果你已经填好了 `config.yaml`，也可以直接运行整条文本管线：

```bash
python "process/run_text_pipeline.py" --config "config.yaml"
```

该命令会顺序完成：

- 联系人发现并导出 `contacts.json`
- 目标联系人文本提取并导出 `messages.normalized.jsonl`
- Few-shot、RAG 与 ChromaDB 产物构建

### 5. 配置本地模型与 Agent

建议在 `config.yaml` 中至少约定这些字段：

```yaml
wechat:
  target_wxid: "wxid_xxx"
  export_dir: "C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output"
  account_wxid: "wxid_your_account"

output:
  base_dir: "data/outputs"

llm:
  endpoint: "http://localhost:11434"
  model: "qwen2.5:7b"
  temperature: 0.7
  timeout_seconds: 120

retrieval:
  chroma_dir: "models/chroma_db"
  top_k: 5

conversation:
  history_limit: 10
  fewshot_limit: 20

dataset:
  min_text_length: 4
  fewshot_limit: 300

embedding:
  model_name: "BAAI/bge-small-zh-v1.5"
  chroma_dir: "models/chroma_db"
```

> 以上仅为 README 中的配置约定示例，用于说明关键参数含义；不代表仓库当前已经完整实现这些字段的解析逻辑。

### 5.1 生成第二阶段单轮文本回复

第二阶段已经提供最小可用的本地文本回复链路：`RAG 检索 + Prompt 组装 + Ollama 生成`。

先确保：

- 第一阶段已经跑通，至少存在 `fewshot.json`、`rag_corpus.jsonl` 和 `models/chroma_db/`
- 本地 `Ollama` 已启动，并且已经拉取对应模型

最小调用示例：

```bash
python "agent/generate_reply.py" `
  --config "config.yaml" `
  --message "今晚回来吃饭吗"
```

如果你希望把最近对话窗口也带入生成链路，可以先准备一个历史文件，例如 `history.json`：

```json
[
  { "role": "user", "text": "你到哪了" },
  { "role": "assistant", "text": "马上到" }
]
```

然后这样调用：

```bash
python "agent/generate_reply.py" `
  --config "config.yaml" `
  --message "今晚回来吃饭吗" `
  --history-file "history.json" `
  --output "data/outputs/wxid_target_contact/reply.debug.json"
```

命令会：

- 从 `fewshot.json` 读取风格样本
- 从 `models/chroma_db/` 检索相关历史表达
- 拼接最近对话窗口
- 调用本地 `Ollama` 输出单轮回复

如果指定 `--output`，会额外落盘调试信息，包括：

- `reply`
- `rag_records`
- `system_prompt`
- `user_prompt`

### 6. 接入微信私聊

项目目标接入方案为：`OpenClaw + 微信 ClawBot 官方插件`。

- 文本消息是当前最稳定、最适合优先落地的能力；
- 语音回复、表情自动发送等能力应根据官方插件开放能力与本地 Skill 实现情况逐步接入；
- 具体安装与绑定命令请以官方最新文档为准。

## 建议目录结构

以下目录结构描述的是项目目标组织方式，用于约定数据与模块边界：

```text
afterglow-robot/
├── agent/
│   ├── __init__.py
│   └── generate_reply.py   # 二阶段单轮文本回复 CLI
├── data/
│   ├── raw/                # 原始解密后的 DB 文件（不入 git）
│   ├── voice_raw/          # 原始 SILK 语音文件
│   ├── voice_processed/    # 处理后的 WAV 片段
│   ├── chat_export.json    # 导出的聊天记录
│   └── db_key.txt          # 数据库密钥（不入 git）
├── process/
│   ├── extract_chat.py     # 按 wxid 筛选聊天记录
│   ├── build_dataset.py    # 构造 Few-shot 样本集与向量库
│   ├── discover_contacts.py
│   └── run_text_pipeline.py
├── afterglow_robot/
│   ├── config.py           # 配置加载
│   ├── wechat_export.py    # SQLite 提取逻辑
│   ├── dataset_builder.py  # Few-shot / RAG 构建
│   ├── rag_retriever.py    # 二阶段检索逻辑
│   ├── llm_client.py       # Ollama API 封装
│   └── reply_generator.py  # 回复生成逻辑
├── config.yaml
└── README.md
```

## 硬件要求

| 组件 | 最低配置 | 推荐配置 |
| --- | --- | --- |
| GPU | `RTX 3060 12G` | `RTX 4070 16G` |
| 内存 | `16 GB` | `32 GB` |
| 存储 | `50 GB SSD` | `100 GB SSD` |
| 系统 | `Windows 10/11 64-bit` | `Windows 11` |

经验预估：

- `Ollama + Qwen2.5-7B` 在 `RTX 3060 12G` 上具备可用的本地推理能力；
- `GPT-SoVITS` 推理通常还需要额外 `4–6 GB` 显存；
- 更推荐将 LLM 与 TTS 设计为分时调用，而不是长时间并行占满显存。

## 当前限制

开源说明中需要明确以下限制，避免误解：

- 当前最稳妥的目标能力是**文字私聊回复**；
- 语音回复与表情自动发送属于**接入中 / 受官方能力限制**的扩展能力；
- 微信官方插件开放范围、灰测状态、平台差异（例如 iOS / Android）可能持续变化；
- 项目默认面向**一对一私聊**，不以群聊场景为优先目标；
- 即使消息通过官方协议中转，项目仍应按高隐私敏感度应用来设计与使用。

## Roadmap

- [x] 完成聊天导出与 Few-shot 数据集构造脚本
- [x] 完成 `ChromaDB` 向量检索链路
- [x] 完成本地 `Ollama` 文本回复最小链路
- [ ] 完成 `EchoSoul Skill` 与 `Ollama` 的联调
- [ ] 完成表情向量索引与排序策略
- [ ] 完成语音预处理与 TTS 接口接入
- [x] 增补 `.gitignore`、示例配置与最小可运行说明

## Contributing

欢迎围绕以下方向提交 Issue 或 PR：

- 数据清洗与样本构造质量；
- 本地推理延迟优化；
- TTS 音质改进与低显存适配；
- 表情检索策略与多模态调度；
- 面向授权纪念场景的产品边界与文档完善。

---

## English Overview

`afterglow-robot` is a **local-first private AI agent workflow for authorized memorial use**. It is designed to run on a user-owned Windows PC and process WeChat chat history, voice samples, and emoji usage patterns locally, so that a style-aware text agent and an optional voice clone can be built without sending the core data off the machine.

### Intended Use

- personal self-archiving and memorialization;
- family-approved remembrance scenarios;
- local research or prototyping within legal and platform constraints.

Do **not** use this project for impersonation, harassment, fraud, unauthorized voice cloning, or any privacy-invasive automation.

### Stack

- Data extraction: `wx_key`, `WeChatDataAnalysis`
- Processing: `Python`, `silk-v3-decoder`, `ffmpeg`, `noisereduce`
- Models: `Ollama`, `Qwen2.5-7B`, `GPT-SoVITS` / `CosyVoice2`, `CLIP`
- Agent runtime: `OpenClaw` + custom `EchoSoul Skill`
- Messaging: WeChat `ClawBot` plugin over `iLink`

### Recommended Pipeline

1. Extract the SQLCipher key on the authorized device.
2. Decrypt and export chat data with `WeChatDataAnalysis`.
3. Preprocess WeChat voice messages from `SILK v3` to clean `WAV`.
4. Build a curated Few-shot dataset plus a `ChromaDB` vector store.
5. Vectorize emoji assets with `CLIP`.
6. Connect the local LLM and optional TTS backend to `OpenClaw`.

### Default Export Path Example

```text
C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output
```

This is a common default path example for the current environment. Real paths may differ across machines and versions, so it should remain configurable.

### Current Project Status

- This repository currently documents the intended architecture and data contracts.
- Text reply is the primary target capability.
- Voice reply and automatic emoji sending are planned / integration-dependent features.
- The repository should be treated as an open-source project skeleton rather than a completed turnkey product.
