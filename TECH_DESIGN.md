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
→ preprocess 清洗与构建 few-shot / rag_corpus / persona_prompt
→ vectorstore 写入 Chroma
→ chat 用本地 Ollama 调试回复
→ wechat-connect 准备 OpenClaw 与微信扫码接入
→ 微信文本消息进入本地回复链路
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

embedding:
  model_name: "BAAI/bge-small-zh-v1.5"
  chroma_dir: "models/chroma_db"

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
- `wechat.export_dir` 必须是存在的本地目录
- `embedding.chroma_dir` 必须可写
- `retrieval.top_k` 必须大于 0
- `conversation.history_limit` 必须大于 0

## 5. 数据模型

### 5.1 标准消息模型

`messages.normalized.jsonl` 中每条记录固定包含：

```json
{
  "message_id": "msg-001",
  "timestamp": 1710000000,
  "sender_role": "target",
  "sender_wxid": "wxid_target",
  "conversation_id": "conv-001",
  "message_type": "text",
  "text": "今天早点睡"
}
```

字段约束：

- `sender_role` 只能是 `self` 或 `target`
- `message_type` 一期固定只保留 `text`
- `text` 必须为清洗后的纯文本

### 5.2 RAG 记录模型

`rag_corpus.jsonl` 中每条记录固定包含：

```json
{
  "id": "rag-001",
  "context": "你到家了吗",
  "text": "刚到，准备洗澡",
  "timestamp": 1710000001,
  "target_wxid": "wxid_target",
  "source_message_id": "msg-001"
}
```

### 5.3 Few-shot 样本模型

`fewshot.json` 每条记录固定包含：

```json
{
  "context": "晚饭吃了吗",
  "response": "刚吃完"
}
```

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

- 仅使用相邻上下文可恢复的对话
- 保留“上文一句 + 目标回复一句”的简单结构
- 限制条数，优先保留信息密度较高样本

### 6.5 Persona Prompt 生成规则

persona prompt 必须包含：

- 目标称呼占位
- 风格约束
- 回复长度偏好
- 禁止暴露 AI 身份
- 禁止编造明确记忆

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
- few-shot 构建
- RAG 记录构建
- prompt 组装

### 9.2 集成测试

覆盖：

- `ingest` 从导出目录生成全部文本产物
- `chat` 调试命令返回文本
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
