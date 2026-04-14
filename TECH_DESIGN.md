# Afterglow Robot Technical Design

## 1. 设计目标

本设计文档用于约束一期实现方案，确保后续开发者不需要再做高层决策。

固定前提：

- 一期只做文本链路
- 数据导出由用户手工完成
- 运行环境为本地 Windows
- 技术路线固定为 `Python + Ollama + Chroma + OpenClaw`

## 2. 系统概览

### 2.1 总体链路

```text
用户提供 target_wxid + wechat_export_dir
→ init 检查环境与依赖
→ ingest 解析导出目录并发现联系人
→ ingest 提取目标文本消息
→ preprocess 清洗并生成 truth / retrieval / voice 分层产物
→ vectorstore 写入 Chroma
→ chat 用本地 Ollama 调试回复
→ wechat-connect 准备 OpenClaw 与微信扫码接入
→ serve 启动本地桥接服务
→ 微信文本消息进入本地回复链路并回传文本回复
```

### 2.2 模块划分

#### installer
职责：

- 检查 `Python`、`Node.js`、`npx`、`Ollama`
- 调用 PowerShell 安装脚本
- 校验 OpenClaw 与微信插件前置条件

禁止：

- 处理业务数据
- 解析聊天记录

#### ingestion
职责：

- 识别导出目录结构
- 发现联系人
- 识别账号
- 提取目标文本消息
- 解析 `self`

#### preprocess
职责：

- 过滤无效文本
- 短句合并
- 构建 few-shot 样本
- 构建 RAG 记录
- 生成 persona prompt

#### vectorstore
职责：

- 调用 embedding 模型
- 写入 `Chroma`
- 执行检索

限制：

- 不保存原始消息作为唯一真相源

#### rag
职责：

- 检索相关历史表达
- 组装 `system_prompt`
- 组装 `user_prompt`

#### wechat_bridge
职责：

- 管理 OpenClaw 侧接入配置
- 转发微信消息到本地回复服务
- 回写文本回复

#### runtime
职责：

- 启动顺序编排
- 错误码管理
- 健康检查
- 日志管理

## 3. CLI 设计

一期统一定义 4 个 CLI 入口。

### 3.1 `init`
用途：

- 检查环境
- 生成配置模板
- 安装或提示安装依赖

输入：

- `--config`
- `--force-check`

输出：

- 环境检查结果
- 配置模板文件
- 安装建议或安装日志

### 3.2 `ingest`
用途：

- 读取聊天目录
- 发现联系人
- 提取目标文本
- 构建 few-shot 与向量库

输入：

- `--config`
- `--target-wxid`
- `--export-dir`

输出：

- `contacts.json`
- `messages.normalized.jsonl`
- `fewshot.json`
- `rag_corpus.jsonl`
- `persona_prompt.txt`
- `truth/dialog_turns.jsonl`
- `truth/persona_profile.json`
- `voice/utterances.normalized.jsonl`
- `retrieval/fewshot_candidates.jsonl`
- `artifacts/manifest.json`
- `models/chroma_db/`

### 3.3 `chat`
用途：

- 本地调试单轮文本回复

输入：

- `--config`
- `--message`
- `--history-file`
- `--output`

输出：

- 终端回复文本
- 可选调试 JSON

### 3.4 `wechat-connect`
用途：

- 检查或安装 OpenClaw
- 检查微信插件接入前置条件
- 输出扫码说明

输入：

- `--config`
- `--check-only`

输出：

- 接入状态
- 安装日志
- 扫码准备说明

### 3.5 `serve`
用途：

- 启动本地微信桥接服务
- 接收 OpenClaw 文本事件
- 调用现有 RAG + persona + Ollama 链路
- 回传文本回复

输入：

- `--config`
- `--host`
- `--port`
- `--once-file`（单次处理调试）

输出：

- HTTP 服务（`/health`、`/openclaw/event`）
- 文本回复 payload
- 桥接日志

## 4. 配置结构

统一使用 `config.yaml`。

### 4.1 最小配置

```yaml
wechat:
  export_dir: "C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output"
  account_wxid: "wxid_owner"
  target_wxid: "self"

output:
  base_dir: "data/processed"

dataset:
  min_text_length: 4
  fewshot_limit: 300

embedding:
  provider: "sentence_transformers"
  model_name: "BAAI/bge-small-zh-v1.5"
  chroma_dir: "models/chroma_db"
  allow_fallback: true
  fallback_provider: "hash"

retrieval:
  top_k: 5

llm:
  endpoint: "http://localhost:11434"
  model: "qwen2.5:7b"
  temperature: 0.7
  timeout_seconds: 120

conversation:
  history_limit: 10
  fewshot_limit: 20
```

### 4.2 配置约束

- `wechat.target_wxid` 允许值为普通微信号或 `self`
- `wechat.export_dir` 必须非空，实际存在性在运行阶段校验
- `embedding.provider` / `embedding.fallback_provider` 目前只允许 `sentence_transformers` 或 `hash`
- `embedding.chroma_dir` 必须非空，实际可写性在运行阶段校验
- `retrieval.top_k` 必须大于 0
- `conversation.history_limit` 必须大于 0

## 5. 数据模型

### 5.1 标准消息模型

`truth/messages.normalized.jsonl` 中每条记录固定包含：

```json
{
  "message_id": "msg-001",
  "timestamp": 1710000000,
  "sender_role": "target",
  "sender_wxid": "wxid_target",
  "conversation_id": "conv-001",
  "message_type": "text",
  "text": "今天早点睡",
  "display_text": "今天早点睡",
  "normalized_text": "今天早点睡",
  "text_length": 5,
  "turn_index": 1,
  "prev_message_id": "",
  "next_message_id": "msg-002",
  "source_parser": "wechat_data_analysis_v1"
}
```

字段约束：

- `sender_role` 在结构化真相源中允许 `target` 或 `counterpart`
- `message_type` 一期固定只保留 `text`
- `text` / `normalized_text` 必须为清洗后的纯文本
- `display_text` 保留更接近原始展示的文本形态
- `prev_message_id` / `next_message_id` / `turn_index` 用于 few-shot、persona 与语音扩展追溯
- 根目录兼容输出 `messages.normalized.jsonl` 仍保留 target-only 语义，供旧 CLI / 脚本继续消费

### 5.2 对话轮次模型

`truth/dialog_turns.jsonl` 每条记录固定包含：

```json
{
  "turn_id": "turn-000001",
  "conversation_id": "conv-001",
  "context_message_id": "msg-001",
  "response_message_id": "msg-002",
  "context": "你到家了吗",
  "response": "刚到，准备洗澡",
  "normalized_context": "你到家了吗",
  "normalized_response": "刚到，准备洗澡",
  "timestamp": 1710000001
}
```

### 5.3 RAG 记录模型

`retrieval/rag_corpus.jsonl` 与兼容输出 `rag_corpus.jsonl` 中每条记录固定包含：

```json
{
  "id": "rag-001",
  "turn_id": "turn-000001",
  "context": "你到家了吗",
  "text": "刚到，准备洗澡",
  "timestamp": 1710000001,
  "target_wxid": "wxid_target",
  "source_message_id": "msg-002"
}
```

### 5.4 Few-shot 样本模型

`retrieval/fewshot.json` 与兼容输出 `fewshot.json` 每条记录固定包含：

```json
{
  "context": "晚饭吃了吗",
  "response": "刚吃完"
}
```

`retrieval/fewshot_candidates.jsonl` 额外保存打分候选，包含 `score`、`reasons`、`turn_id` 与消息追溯信息，用于可解释筛选。

### 5.5 Persona / Voice 派生产物

- `truth/persona_profile.json`：基于语料统计的人设画像，包含长度偏好、句末标点、语气词、emoji、提问句占比、直接回应/解释型倾向等字段；
- `voice/utterances.normalized.jsonl`：面向未来语音能力的规范化文本留档，包含语气词、emoji、句末标点、是否疑问句等可恢复特征；
- `artifacts/manifest.json`：记录 ingest 时间、解析器、目标 wxid、embedding 实际 provider、是否 fallback、产物计数。

### 5.6 微信桥接事件模型（最小实现）

输入事件最小字段：

- `conversation_id`
- `sender_id`
- `message_type`（一期仅支持 `text`）
- `text`
- `timestamp`

输出事件最小字段：

- `conversation_id`
- `status`（`ok`/`error`）
- `reply_text`（成功时）
- `error.code`、`error.message`（失败时）

## 6. 处理规则

### 6.1 联系人与账号识别

- 单账号导出目录：自动识别 `account_wxid`
- 多账号导出目录：必须要求用户显式指定 `account_wxid`

### 6.2 目标筛选规则

- 若 `target_wxid != self`：提取该联系人发送的文本消息
- 若 `target_wxid == self`：提取号主本人发送的文本消息

### 6.3 文本过滤规则

一期固定过滤：

- 系统消息
- 空文本
- 非文本消息
- 过短低信息文本

默认最小文本长度由配置项控制，建议默认值为 `4`。

### 6.4 Few-shot 构建规则

- 先从 `dialog_turns` 生成完整候选，再写入 `retrieval/fewshot_candidates.jsonl`
- 打分仅使用确定性特征：文本完整度、风格代表性、重复惩罚、多样性约束、轻度近期加权
- 最终 `fewshot.json` 仍保持兼容结构，供 runtime 直接消费

### 6.5 Persona Prompt 生成规则

- persona prompt 基于 `persona_profile.json` 渲染，而不是固定模板
- 至少体现：目标称呼占位、回复长度偏好、表达倾向、句末标点偏好、语气词/emoji 偏好
- 当某类统计不足时，只省略对应字段，不整体回退为固定模板
- 必须继续包含“禁止暴露 AI 身份”“禁止编造明确记忆或未经提供的事实”

### 6.6 Embedding 与回退规则

- 默认 provider 为 `sentence_transformers`
- 若缺少依赖或模型加载失败，且 `embedding.allow_fallback=true`，自动降级到 `hash`
- 若 `allow_fallback=false`，直接报错，不做静默回退
- Chroma collection metadata 会记录 `embedding_schema_version`、实际 `embedding_provider` 与 `embedding_model`
- 查询阶段若 schema、provider 或 model_name 任一不一致，或旧库缺少 metadata，直接要求重新执行 `ingest`

## 7. 在线回复设计

### 7.1 Prompt 组装

固定顺序：

1. `system_prompt`
2. few-shot 样本
3. RAG 检索结果
4. 最近对话窗口
5. 当前用户消息

### 7.2 回复生成

- 使用本地 `Ollama`
- 默认单轮文本输出
- 不返回推理过程

### 7.3 错误处理

必须明确区分以下错误：

- 配置缺失
- 导出目录不存在
- 账号未识别
- 目标联系人不存在
- 向量库未构建
- `Ollama` 未启动
- OpenClaw 未安装
- OpenClaw 请求格式错误
- OpenClaw 非文本消息
- OpenClaw 回写失败

错误输出要求：

- 面向用户的简短错误提示
- 面向日志的详细错误上下文

## 8. 文件与目录约定

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
│  ├─ install_ollama.ps1
│  ├─ install_openclaw.ps1
│  └─ bootstrap.ps1
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

## 9. 测试设计

### 9.1 单元测试

覆盖：

- 账号识别
- 联系人发现
- `self` 解析
- 文本过滤
- truth/dialog_turns / voice utterances 生成
- persona_profile 统计
- few-shot 打分与去重
- RAG 记录构建
- embedding fallback 与 provider mismatch
- prompt 组装

### 9.2 集成测试

覆盖：

- `ingest` 从导出目录生成全部文本产物
- `chat` 调试命令返回文本
- `serve` 接收文本事件并返回回复 payload，且真实历史进入 prompt
- 缺少配置或依赖时的错误输出

### 9.3 安装链路测试

覆盖：

- `init` 在缺少 `Node.js` / `Ollama` 时给出明确动作
- `wechat-connect` 可完成接入前检查

## 10. 后续扩展点

仅预留接口，不纳入一期实现：

- `tts`：文本转语音
- `voice_sender`：语音发送
- `emoji_selector`：表情推荐与发送

扩展原则：

- 不破坏文本主链路
- 不改变本地优先原则
- 不把实验性能力混入一期主命令
