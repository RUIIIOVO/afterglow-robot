# Afterglow Robot

一个面向**本地优先、授权纪念用途**的微信文本风格复刻项目规划。  
目标是让用户提供：

- 目标微信号（或 `self` 表示号主本人）
- 已解密并导出的微信聊天记录目录

系统随后完成文本数据提取、清洗、索引、RAG 配置、本地模型接入与 OpenClaw 微信接入，使用户在微信里与“该人物表达风格”的机器人进行**文本聊天**。


## 1. 项目定位

- 基于用户**自行导出且已授权**的数据
- 在**本地环境**内处理聊天记录
- 通过 **RAG + Prompt** 的方式复现目标人物的常见表达风格
- 第一阶段只支持**文本聊天**

## 2. 一期目标

用户只需要输入：

- `target_wxid`：目标微信号，或 `self`
- `wechat_export_dir`：解密后的微信聊天记录目录，例如  
  `C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output`

系统应完成：

1. 检查运行环境
2. 安装或校验 `Node.js`、`npx`、`Ollama`、`OpenClaw`
3. 读取微信导出目录
4. 发现联系人并筛选目标微信号的文本消息
5. 清洗文本并构建 few-shot 与 RAG 语料
6. 写入本地结构化数据与 `Chroma` 向量索引
7. 生成人设提示词 `persona_prompt.txt`
8. 配置 `Ollama`
9. 通过 `@tencent-weixin/openclaw-weixin-cli` 接入微信
10. 输出扫码连接说明

## 3. 一期不做

以下能力不进入一期正式交付：

- 语音生成
- 语音发送
- 表情自动发送
- 模型微调
- 群聊支持
- 云端部署
- GUI 桌面界面

后续文档中只为这些能力保留接口与目录约定，不实现具体链路。

## 4. 合规与隐私边界

本项目只能用于以下前提下的本地实验或纪念用途：

- 用户对数据拥有合法访问权
- 目标人物已授权，或该场景符合法律与伦理要求
- 数据处理范围、使用方式与本地法规相符

请勿将本项目用于：

- 未授权身份冒充
- 骚扰、欺诈、诱导交流
- 未经许可的数据抓取、隐私处理或语音克隆
- 违反微信平台规则或当地法律法规的自动化行为

设计约束：

- 默认所有数据只保存在本地
- 默认不上传云端
- 日志中避免输出完整敏感原文
- 后续实现需提供本地索引和缓存清理能力

## 5. 推荐技术路线

一期固定技术路线如下：

- 编排语言：`Python`
- 本地模型：`Ollama`
- 向量数据库：`Chroma`
- 微信接入：`OpenClaw` + `@tencent-weixin/openclaw-weixin-cli`
- 配置文件：`config.yaml`
- 安装与初始化：`Python CLI + PowerShell`

RAG 方案固定为：

- 原始结构化消息存本地文件
- 向量库只存切分后的语义片段与元数据
- 通过 `Prompt + Few-shot + 检索结果 + 当前会话上下文` 生成回复

## 6. 数据准备步骤

本项目**不负责**微信数据导出工具的实现。  
用户需要先手工完成以下步骤。

### 6.1 使用 `wx_key` 获取数据库密钥

1. 在目标 Windows 机器上登录微信 PC 客户端
2. 下载并运行 `wx_key`
3. 从运行中的微信进程中读取数据库密钥
4. 妥善保存密钥，仅用于本地解密

建议：

- 在原始授权设备上完成此操作
- 不要将密钥上传到云端或共享给他人

### 6.2 使用 `WeChatDataAnalysis` 解密并导出聊天记录

1. 打开 `WeChatDataAnalysis`
2. 选择微信数据目录
3. 填入通过 `wx_key` 获取的数据库密钥
4. 执行数据库解密与聊天记录导出
5. 确认输出目录可访问

常见默认导出目录示例：

`C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output`

说明：

- 实际路径可能因机器环境、软件版本而不同
- 后续系统会要求用户显式填写这个目录

### 6.3 明确目标对象

后续系统会要求输入：

- 目标微信号，例如某个联系人 `wxid_xxx`
- 或输入 `self`，表示提取号主本人发送的全部文本消息

## 7. CLI 入口

后续实现统一使用以下 4 个入口：

- `init`：环境检查、依赖安装、生成配置模板
- `ingest`：发现联系人、提取目标消息、构建 few-shot 与向量库
- `chat`：本地单轮文本调试
- `wechat-connect`：安装或校验 OpenClaw 与微信连接准备

为了完成微信文本聊天闭环，当前仓库额外提供：

- `serve`：启动本地微信桥接服务，接收 OpenClaw 文本事件并回传文本回复

其中 `wechat-connect` 负责安装/校验接入依赖，`serve` 才是实际收发消息服务。

## 8. 规划中的核心产物

数据处理完成后，系统应产出：

- `contacts.json`
- `messages.normalized.jsonl`
- `fewshot.json`
- `rag_corpus.jsonl`
- `persona_prompt.txt`
- `models/chroma_db/`

当前实现还会在 `output.base_dir` 下生成分层产物：

- `truth/contacts.json`
- `truth/messages.normalized.jsonl`
- `truth/dialog_turns.jsonl`
- `truth/persona_profile.json`
- `voice/utterances.normalized.jsonl`
- `retrieval/rag_corpus.jsonl`
- `retrieval/fewshot_candidates.jsonl`
- `retrieval/fewshot.json`
- `persona/persona_prompt.txt`
- `artifacts/manifest.json`

分层约定如下：

- `truth/`：结构化真相源，作为后续 persona、few-shot、语音扩展的统一上游；
- `retrieval/`：仅保存检索与 few-shot 选择所需的派生语料；
- `voice/`：保存面向未来语音能力的规范化文本留档；
- 根目录旧文件：为当前 CLI 与既有脚本保留兼容输出，其中 `messages.normalized.jsonl` 仍是 target-only 兼容语料，不等同于 `truth/messages.normalized.jsonl`。

## 9. 推荐目录结构

以下为后续实现建议结构：

```text
afterglow-robot/
├─ README.md
├─ PRD.md
├─ TECH_DESIGN.md
├─ config/
│  └─ config.example.yaml
├─ data/
│  ├─ raw/
│  ├─ processed/
│  ├─ persona/
│  └─ vectorstore/
├─ scripts/
│  ├─ install_python.ps1
│  ├─ install_node.ps1
│  ├─ install_ollama.ps1
│  ├─ install_openclaw.ps1
│  ├─ bootstrap.ps1
│  └─ start.ps1
├─ src/
│  ├─ installer/
│  ├─ ingestion/
│  ├─ preprocess/
│  ├─ vectorstore/
│  ├─ rag/
│  ├─ wechat_bridge/
│  ├─ runtime/
│  └─ cli/
└─ logs/
```

## 10. 开发顺序

建议严格按以下顺序推进：

1. 固化文档规格
2. 实现离线文本导入链路
3. 实现 `persona_prompt` 与本地 `chat` 调试链路
4. 实现 `init` 与 `wechat-connect`
5. 联通微信文本消息闭环
6. 仅预留语音扩展接口

## 11. 下一步

当前仓库已提供以下规格文档：

- `README.md`
- `PRD.md`
- `TECH_DESIGN.md`

推荐后续开发直接以这三份文档为准，先补齐 CLI 和模块骨架，再进入实现阶段。

## 12. 一期最小可运行版本（当前仓库）

当前仓库已实现一期最小链路（文本链路）：

- `init`
- `ingest`
- `chat`
- `wechat-connect`
- `serve`

### 12.1 安装依赖

```bash
python -m pip install -e ".[embeddings]"
```

如未使用 `-e`，至少需要：

- `PyYAML`
- `chromadb`
- `sentence-transformers`

### 12.2 准备配置

```bash
copy config/config.example.yaml config/config.yaml
```

按实际路径修改：

- `wechat.export_dir`
- `wechat.account_wxid`（多账号必填）
- `wechat.target_wxid`

`embedding` 段当前支持：

- `embedding.provider`：默认 `sentence_transformers`
- `embedding.model_name`
- `embedding.allow_fallback`：默认 `true`
- `embedding.fallback_provider`：默认 `hash`

当前配置校验会额外检查：

- `wechat.export_dir`、`wechat.target_wxid`、`output.base_dir`、`embedding.*` 不允许为空；
- `embedding.provider` / `embedding.fallback_provider` 目前只允许 `sentence_transformers` 或 `hash`；
- `llm.endpoint` 必须是合法 `http/https` URL；
- `llm.temperature` 必须在 `0-2`；
- 所有数量与超时字段必须大于 `0`。

真实 embedding 的当前策略：

- 默认优先使用 `SentenceTransformers` 加载 `embedding.model_name`；
- 若缺少 `sentence-transformers` 依赖、模型下载失败或模型加载失败，且 `embedding.allow_fallback=true`，会清晰告警并降级到 `hash`；
- 若已构建向量库的 embedding schema、provider 或 model_name 与当前运行配置不一致，系统会要求重新执行 `ingest`，避免混用不同向量空间；旧库缺少这些 metadata 时也会视为不兼容；
- `artifacts/manifest.json` 会记录实际使用的 embedding provider、是否发生降级及各类产物计数。

### 12.3 当前支持的导出结构与兼容策略

当前同时支持两类输入：

1. 测试用最小结构 `minimal_v1`

```text
<wechat_export_dir>/
└─ accounts/
   └─ <account_wxid>/
      ├─ contacts.json
      └─ messages.jsonl
```

2. `WeChatDataAnalysis` 真实导出产物（推荐）

- 解压目录：

```text
<wechat_export_dir>/
├─ manifest.json
└─ conversations/
   └─ <conversation>/
      ├─ meta.json
      ├─ messages.json
      └─ messages.txt
```

- 或直接传入单个导出 ZIP 文件路径：

```text
<wechat_export_zip>.zip
```

当前兼容策略如下：

- 优先支持 `messages.json`，保留 `minimal_v1` 向后兼容；
- `messages.txt` 走 best-effort 解析，主要覆盖文本与系统消息；
- 若 `schemaVersion` 缺失，按 v1 处理；
- 若导出启用了 `privacy mode`，通常会隐藏 `account` / `username`，当前不作为可 ingest 输入；
- `messages.html` 暂不参与 ingest。

说明：由于不同版本 `WeChatDataAnalysis` 的导出细节可能存在差异，当前实现基于仓库公开导出逻辑与常见目录模式兼容设计；若你的导出目录与上述结构不同，请优先保留 `manifest.json` 与 `conversations/*/messages.json` 再接入本项目。

### 12.4 命令示例

```bash
python -m src.cli.main init --config config/config.yaml
python -m src.cli.main ingest --config config/config.yaml
python -m src.cli.main chat --config config/config.yaml --message "今天怎么样？"
python -m src.cli.main wechat-connect --config config/config.yaml --check-only --bridge-url "http://127.0.0.1:8787/openclaw/event"
python -m src.cli.main wechat-connect --config config/config.yaml --bridge-url "http://127.0.0.1:8787/openclaw/event"
python -m src.cli.main serve --config config/config.yaml --host 127.0.0.1 --port 8787
```

一键检查并启动（Windows PowerShell）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

说明：`start.ps1` 默认会自动安装缺失依赖（Python / Node.js / Ollama / OpenClaw），自动拉起本地 `Ollama` 服务，并按 `config.yaml` 自动拉取缺失模型；缺少 ingest 产物时会自动执行 `ingest`。
若配置里的 `wechat.export_dir` 当前不可用，`start.ps1` 会自动回退到 `tests/fixtures/single_account` 做本地演示跑通。

指定监听地址与端口：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -BindHost 127.0.0.1 -Port 8787
```

仅做检查不启动服务：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -CheckOnly
```

OpenClaw 安装命令（一期固定）：

```bash
npx -y @tencent-weixin/openclaw-weixin-cli@latest install
```

桥接服务单次调试（不常驻）：

```bash
python -m src.cli.main serve --config config/config.yaml --once-file tests/fixtures/bridge_event.json
```

### 12.5 从 ingest 到微信聊天最小跑通步骤

1. 生成语料与向量库：`python -m src.cli.main ingest --config config/config.yaml`
2. 检查或安装 OpenClaw，并自动写入桥接配置：`python -m src.cli.main wechat-connect --config config/config.yaml --bridge-url "http://127.0.0.1:8787/openclaw/event"`
3. 启动本地桥接服务：`python -m src.cli.main serve --config config/config.yaml --host 127.0.0.1 --port 8787`
4. 扫码完成后，向目标联系人发送一条文本消息，确认 OpenClaw 已把私聊文本转发到本地 `POST /openclaw/event`

如果你已经装好了官方 `openclaw-weixin` 渠道插件，但本地 `wechat-connect` 没有成功补丁旧安装目录，可手工执行兜底脚本：

```bash
python scripts/patch_openclaw_weixin_for_afterglow.py --bridge-url "http://127.0.0.1:8787/openclaw/event"
```

该脚本会：

- 给 `channels.openclaw-weixin.afterglow` 写入直连配置；
- 把本地安装的 `openclaw-weixin` 插件切换为“优先调用 afterglow-robot 本地桥接服务”；
- 保留官方微信渠道收发能力，但不再默认把私聊文本交给 OpenClaw 主 Agent。
5. 微信发来文本消息后，服务调用现有 `RAG + persona + Ollama` 链路并回传文本回复

`scripts/start.ps1` 也已切换到正式入口：它会调用 `wechat-connect --bridge-url ...`，不再要求你额外手工跑一次补丁脚本。

### 12.6 真实微信环境联调与验收

推荐按以下顺序验收：

1. 在 `WeChatDataAnalysis` 中导出 **JSON** 或 **TXT** 格式聊天记录；
2. 将 `wechat.export_dir` 指向导出目录，或直接指向单个导出 ZIP；
3. 运行 `python -m src.cli.main ingest --config config/config.yaml`，确认输出中出现 `解析器：wechat_data_analysis_v1` 或 `minimal_v1`；
4. 运行 `python -m src.cli.main wechat-connect --config config/config.yaml --bridge-url "http://127.0.0.1:8787/openclaw/event"`；
5. 运行 `python -m src.cli.main serve --config config/config.yaml --host 127.0.0.1 --port 8787`；
6. 在微信里向目标联系人发送文本消息；
7. 检查控制台、`logs/wechat_bridge.log` 与微信回包内容。

建议验收标准：

- `ingest` 能自动识别单账号导出；
- `contacts.json`、`messages.normalized.jsonl`、`fewshot.json`、`rag_corpus.jsonl`、`persona_prompt.txt` 全部生成；
- `truth/persona_profile.json`、`truth/dialog_turns.jsonl`、`voice/utterances.normalized.jsonl`、`retrieval/fewshot_candidates.jsonl`、`artifacts/manifest.json` 全部生成；
- `wechat-connect` 输出桥接补丁结果，而不是要求手工改 OpenClaw 文件；
- 微信文本消息能进入 `/openclaw/event`，并收到本地生成的文本回复；
- 非文本消息、缺少 ingest 产物、OpenClaw 回写失败时，返回明确错误码。

桥接服务会把每个 `conversation_id` 的最近对话以本地 JSONL 形式持久化到：

```text
<output.base_dir>/bridge_history/
```

这些历史会在下一轮微信消息进入时自动注入 `history`，不再是固定空历史调用。

### 12.7 测试

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

说明：若本地缺少 `chromadb`、`Ollama`、`Node.js/npx`，命令会返回明确错误提示，不会伪造成功状态。

### 12.8 当前剩余限制

- `messages.html` 尚未进入 ingest 解析链路；
- `messages.txt` 仅做文本级 best-effort 解析，时间戳与富媒体字段不会完整保留；
- 开启 `privacy mode` 的导出因隐藏账号与联系人标识，当前不建议直接用于 `target_wxid` 精准筛选；
- `SentenceTransformers` 首次使用通常需要联网下载模型；若未安装依赖或模型不可用，会自动降级到 `hash`，效果会明显弱于真实语义 embedding；
- 当前桥接仍只支持文本收发，不包含语音、图片、群聊等高级路由；
- 当前会话历史仅按 `conversation_id` 本地滚动保存，尚未接入去重、摘要压缩或跨设备同步。
