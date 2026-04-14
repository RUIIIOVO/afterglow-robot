# Afterglow Robot TODO

本文档用于落实当前项目的目标、已完成能力与未完成事项，作为后续开发与验收清单。

## 目标范围

当前目标聚焦一期最小可运行版本：

- 用户手工使用 `wx_key` 与 `WeChatDataAnalysis` 导出微信聊天数据
- 用户输入目标微信号或 `self`
- 系统提取目标人物或号主本人的文本消息
- 系统构建结构化产物、RAG 语料、提示词与本地向量库
- 系统自动安装/校验 `Ollama`、`OpenClaw`、`@tencent-weixin/openclaw-weixin-cli`
- 用户扫码连接微信后，可通过本地链路完成文本聊天
- 为后续语音能力预留数据与接口扩展空间

## 已完成

### 文档与使用说明

- [x] 在 `README.md` 中写明 `wx_key` 与 `WeChatDataAnalysis` 的手工操作步骤
- [x] 在 `README.md` 中写明默认导出目录示例 `C:/Users/hyp/AppData/Roaming/wechat-data-analysis-desktop/output`
- [x] 在 `README.md` 中写明一期只支持文本聊天，语音能力暂不实现

### 数据导入与筛选

- [x] 支持通过配置输入 `wechat.target_wxid`
- [x] 支持特殊值 `self`，提取号主本人发送的文本消息
- [x] 支持单账号自动识别
- [x] 支持多账号场景下要求显式指定 `wechat.account_wxid`
- [x] 支持目标联系人文本消息筛选
- [x] 支持过滤系统消息、空文本、非文本消息、过短文本

### 数据产物与检索

- [x] 生成 `contacts.json`
- [x] 生成 `messages.normalized.jsonl`
- [x] 生成 `fewshot.json`
- [x] 生成 `rag_corpus.jsonl`
- [x] 生成 `persona_prompt.txt`
- [x] 生成 `truth/persona_profile.json`
- [x] 生成 `truth/dialog_turns.jsonl`
- [x] 生成 `voice/utterances.normalized.jsonl`
- [x] 生成 `retrieval/fewshot_candidates.jsonl`
- [x] 生成 `artifacts/manifest.json`
- [x] 写入本地 `Chroma` 向量库

### 本地回复链路

- [x] 支持本地 `chat` 调试命令
- [x] 支持从 `persona_prompt.txt`、`fewshot.json`、向量库构建回复上下文
- [x] 支持通过本地 `Ollama` 生成文本回复
- [x] 微信桥接已接入本地真实会话历史，而不再固定传空历史

### 微信接入与启动

- [x] 支持 `wechat-connect` 检查/安装 OpenClaw 接入
- [x] 固定使用 `npx -y @tencent-weixin/openclaw-weixin-cli@latest install`
- [x] 支持 `serve` 启动本地微信桥接服务
- [x] 支持接收 OpenClaw 文本事件并返回文本回复
- [x] 支持 OpenClaw 回写失败、非文本事件、无向量库等错误区分
- [x] `scripts/start.ps1` 已支持自动检查/安装 Python、Node.js、Ollama、OpenClaw
- [x] `scripts/start.ps1` 已支持自动拉起本地 `Ollama` 服务
- [x] `scripts/start.ps1` 已支持自动拉取缺失模型
- [x] `scripts/start.ps1` 已支持缺少 ingest 产物时自动执行 `ingest`
- [x] 已提供 `scripts/patch_openclaw_weixin_for_afterglow.py`，用于把 `openclaw-weixin` 路由到本地桥接服务
- [x] `wechat-connect` 已收口 OpenClaw 桥接补丁逻辑，支持正式命令行参数接入

### 真实可用性补齐

- [x] 支持 `WeChatDataAnalysis` 真实导出目录与导出 ZIP 的解析
- [x] 支持 `messages.json` 优先解析，并兼容 `messages.txt` best-effort 解析
- [x] 已建立导出版本兼容策略说明，并在 README 中写明假设与限制
- [x] 已补充配置校验与首次使用错误提示
- [x] 已补充真实微信环境端到端联调与验收文档
- [x] 已补充解析器测试、配置校验测试、桥接关键路径测试

## 未完成

### P0：影响真实可用性的缺口

- [x] 支持真实 `WeChatDataAnalysis` 导出结构，而不只是当前最小测试目录格式
- [x] 补充更多导出格式解析器，并建立版本兼容策略
- [x] 将当前“OpenClaw + 本地桥接补丁”方案收口为更稳定的正式接入方案
- [x] 完成真实微信环境下的端到端联调与验收文档
- [x] 补充配置校验与用户提示，减少首次启动时的人工判断成本

### P1：影响效果与可扩展性的缺口

- [x] 明确“结构化真相源”与“向量检索语料”的分层存储策略
- [x] 为后续语音能力补充更完整的规范化语料留档，而不仅是当前 RAG 语料
- [x] 引入真实语义 embedding，实现替换当前 `HashEmbeddingFunction` 的占位方案
- [x] 增强 persona 构建逻辑，而不仅是固定模板文本
- [x] 增强 few-shot 选择策略，提高风格复现质量
- [x] 为微信桥接链路接入真实会话历史，而不是当前空历史调用

### P2：后续能力预留

- [ ] 设计并实现语音生成能力接口
- [ ] 设计并实现语音发送链路
- [ ] 设计语音素材、文本语料、说话习惯等统一数据资产结构
- [ ] 预留群聊支持的事件模型与路由策略
- [ ] 预留 GUI 或更友好的初始化交互界面

## 当前结论

- 当前项目已经完成“一期最小文本闭环”的主要骨架
- 当前项目已完成“真实导出兼容 + 正式接入收口 + 数据分层 + persona/few-shot 效果增强 + 会话历史接入”的 P0/P1 主线
- 当前项目仍未完成“历史压缩与去重、语音生成与发送、群聊扩展”等后续能力
- 后续开发优先顺序建议为：`历史增强` → `语音扩展` → `群聊扩展`
