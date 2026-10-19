# CustomServiceAgent：企业级电商客服 Agent

> GitHub：<https://github.com/2040643557/CustomServiceAgent>

一个可直接运行的电商客服 Agent 项目，以「并夕夕 · 智能客服小夕」为场景，覆盖 Agent 工程化的完整技术栈：ReAct + Function Calling、工具调用、MCP、RAG、Multi-Agent 路由、任务规划（Planning）、记忆（Memory）、技能（Skills）与离线评估。

项目默认使用 Mock 电商数据，无需接入真实订单系统，配置一个 OpenAI 兼容的 API Key 即可跑通全部流程。

## 核心能力

| 能力 | 说明 |
|------|------|
| ReAct + Function Calling | LLM 在「思考 → 调用工具 → 观察结果」循环中完成订单、商品、物流、退款等操作 |
| 多轮对话管理 | 历史消息超过阈值后由 LLM 压缩为摘要，会话以 JSON 持久化，重启可恢复 |
| 结构化输出 | 基于 Pydantic 输出意图、置信度、回复、是否转人工、追问问题 |
| RAG 知识库 | Markdown 按二级标题切分 + 本地 BGE Embedding 检索，支持 numpy（JSON 索引）与 Chroma 两种后端 |
| MCP 集成 | 独立 FastMCP Server 通过 Streamable HTTP 暴露工具，连接失败时自动降级到本地工具 |
| Multi-Agent 协作 | Router 将请求分发给售前 / 售后 / 投诉子 Agent，每个子 Agent 拥有独立 prompt 与工具白名单 |
| 任务规划 Planning | 针对多步订单请求执行「生成计划 → 校验 → 执行 → 反思 → 按需重规划 → 生成回答」闭环 |
| 记忆系统 | 短期记忆（会话内事实）+ 长期记忆（跨会话按用户持久化） |
| 技能系统 | 基于 SKILL.md 的能力模块，渐进式披露，按需通过 `load_skill` 加载完整流程 |
| 评估体系 | 沙箱重跑黄金测试集，过程指标 + 结果指标双层评分，可选 LLM-as-judge |
| 离线评测脚本 | 分别评测路由准确率、RAG 文档命中率、Planning 计划合法性与行为符合度 |

## 快速开始

要求 Python 3.11+，以及一个 OpenAI 兼容的 API Key（支持自定义 Base URL）。

```bash
# 1. 获取代码并进入项目
git clone https://github.com/2040643557/CustomServiceAgent.git
cd CustomServiceAgent

# 2. 创建并激活虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# Windows 可使用：copy .env.example .env
```

编辑 `.env`，至少填写：

```ini
OPENAI_API_KEY=sk-your-key
# 可选：使用中转或兼容服务（如 DeepSeek）
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini
# RAG 使用本地 SentenceTransformer 模型，首次运行会自动下载
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
# 国内下载较慢时可启用镜像（也可直接设置 HF_ENDPOINT 环境变量）
# HF_ENDPOINT=https://hf-mirror.com
```

> 使用 DeepSeek 等服务时，额外设置 `LLM_DISABLE_THINKING=true` 可关闭思考模式；OpenAI 官方接口请保持默认 `false`。

```bash
# 5. 构建知识库索引（首次运行一次）
python -m app.scripts.build_kb_index

# 6. 启动对话
python main.py
```

启动后直接输入问题，例如：

- `我的订单还没发货，怎么回事？` —— 订单 + 物流查询
- `有没有适合跑步的运动鞋推荐？` —— 商品推荐技能
- `这条牛仔裤质量有问题，我要退货` —— 退货退款流程
- `查询订单 ORD-20240115-001 是否发货，如果已经发货，再查询物流进度` —— 多步 Planning 流程

每条回复底部会显示 `[意图 | 置信度 | 是否转人工]`。对话中支持以下命令：

| 命令 | 作用 |
|------|------|
| `skills` | 查看已加载的技能模块 |
| `memory` | 查看短期 / 长期记忆 |
| `reset` | 清空当前会话 |
| `quit` / `exit` | 退出 |

## 进阶配置

以下能力通过 `.env` 开关启用，修改后重启程序即可：

| 配置项 | 取值 | 说明 |
|--------|------|------|
| `MULTI_AGENT_ENABLED` | `true` / `false` | 启用 Router + 子 Agent 协作模式 |
| `MCP_ENABLED` | `true` / `false` | 通过 MCP 协议加载工具，需先启动 `python mcp_server/server.py` |
| `MCP_SERVER_URL` | URL | MCP Server 地址，默认 `http://127.0.0.1:9123/mcp` |
| `RAG_BACKEND` | `numpy` / `chroma` | 向量检索后端；依赖 `requirements.txt` 已包含 chromadb |
| `MEMORY_ENABLED` | `true` / `false` | 是否启用短期 / 长期记忆 |
| `MEMORY_USER_ID` | 字符串 | 长期记忆所属用户，按用户分文件存储 |
| `SKILLS_ENABLED` | `true` / `false` | 是否启用 SKILL.md 技能系统 |

使用 Chroma 后端时，需要单独构建对应索引：

```bash
python -m app.scripts.build_kb_index --backend chroma
```

## 架构总览

```text
main.py (CLI)
│
├── 单 Agent 模式（默认）
│   └── EcomAgent
│       └── ReAct 循环
│           ├── ToolManager ── 本地工具 / MCP 工具
│           ├── search_knowledge ── RAG 检索
│           ├── MemoryManager ── 短期记忆 + 长期记忆
│           └── load_skill ── SKILL.md 按需加载
│
└── Multi-Agent 模式（MULTI_AGENT_ENABLED=true）
    └── MultiAgentOrchestrator
        ├── Router ── 售前 / 售后 / 投诉 SubAgent（独立 prompt + 工具白名单）
        └── 多步订单任务
            └── Planner → PlanExecutor → Reflector → ResponseGenerator
```

单 Agent 的一次请求处理流程：

1. 用户输入进入 ReAct 循环，由模型决定调用哪些工具。
2. 工具结果回填后继续推理，直到模型给出最终回复。
3. 通过结构化输出提取意图、置信度、是否转人工等字段。
4. 更新短期记忆；历史过长时自动压缩为摘要。
5. 会话与短期记忆写入 `app/sessions/`。

Multi-Agent 模式下，普通请求由 Router 路由到对应子 Agent；当请求同时包含订单号、发货状态、物流查询和顺序词时，自动进入 Planning 流程：Planner 生成结构化计划并校验工具白名单与步骤顺序，PlanExecutor 按实际工具结果决定后续步骤（例如未发货则跳过物流查询），Reflector 判断 `complete` / `replan` / `clarify`，必要时最多重规划一次，最后由 ResponseGenerator 依据真实执行结果生成回答。

## 工具与技能

内置工具：

| 工具 | 作用 |
|------|------|
| `query_order` | 查询订单状态、商品、金额、物流单号 |
| `query_product` | 按关键词或商品 ID 搜索商品 |
| `query_logistics` | 查询物流轨迹 |
| `apply_refund` | 申请退款（敏感操作） |
| `search_knowledge` | RAG 检索政策与 FAQ |
| `list_user_orders` | 列出当前用户全部订单概要 |
| `recall_user_memory` | 查询用户短期 / 长期记忆 |
| `load_skill` | 按需加载技能完整指令 |
| `get_user_balance` | 查询账户余额 |

内置技能（`app/agent/skills/definitions/`）：

- `process-return`：退货退款处理
- `track-order`：订单物流跟踪
- `product-recommend`：商品推荐

## 项目结构

```text
CustomServiceAgent/
├── main.py                        # CLI 入口，支持单 Agent / Multi-Agent 切换
├── requirements.txt
├── .env.example                   # 环境变量模板
│
├── app/
│   ├── config/settings.py         # 配置管理
│   ├── prompts/                   # 客服、摘要、子 Agent、记忆、评估等 prompt
│   ├── schemas/response.py        # 结构化输出 schema
│   ├── agent/
│   │   ├── chat.py                # 单 Agent ReAct 循环
│   │   ├── summarizer.py          # 历史摘要压缩
│   │   ├── storage.py             # 会话 JSON 持久化
│   │   ├── memory/                # 短期 / 长期记忆
│   │   ├── skills/                # 技能加载器与 SKILL.md 定义
│   │   ├── tools/                 # 工具注册、Mock 数据与具体实现
│   │   └── rag/                   # 切分、Embedding、检索与向量后端
│   ├── mcp_client/                # MCP Client 与 schema 转换
│   ├── multi_agent/
│   │   ├── router.py              # 意图路由
│   │   ├── agents.py              # 子 Agent 定义
│   │   ├── orchestrator.py        # 编排器（含 Planning 分流）
│   │   ├── planner.py             # 任务计划生成与校验
│   │   ├── executor.py            # 计划执行与条件跳过
│   │   ├── reflection.py          # 执行结果评估与重规划判断
│   │   └── response_generator.py  # 基于执行结果生成回答
│   ├── evaluation/                # 黄金测试集、沙箱、指标与评估器
│   └── scripts/
│       ├── build_kb_index.py      # 构建知识库索引
│       ├── run_eval.py            # 端到端评估
│       ├── evaluate_router.py     # 路由准确率评测
│       ├── evaluate_retrieval.py  # RAG 文档命中率评测
│       ├── evaluate_planning.py   # Planning 工作流评测
│       └── plan_order.py          # 单次 Planning 演示
│
├── mcp_server/server.py           # 独立 MCP Server（FastMCP + Streamable HTTP）
├── experiments/                   # 离线评测案例与 Planning 评测报告
├── tests/                         # 端到端与模块测试
└── app/tests/                     # Planning / Router 解析单元测试
```

## 评测与测试

```bash
# 端到端评估：沙箱重跑黄金测试集 + 过程/结果双层指标
python -m app.scripts.run_eval --no-judge   # 仅代码规则，速度快
python -m app.scripts.run_eval              # 含 LLM-as-judge

# 分项离线评测
python -m app.scripts.evaluate_router       # Router 路由准确率与混淆明细
python -m app.scripts.evaluate_retrieval    # RAG Top-K 文档命中率
python -m app.scripts.evaluate_planning     # 计划合法性、步骤顺序、执行行为

# 单次 Planning 演示
python -m app.scripts.plan_order ORD-20240115-001

# 离线单元测试（不调用 LLM）
pytest app/tests
```

`tests/` 下的端到端测试会真实调用 LLM，需要有效的 API Key，按需运行。

评测数据位于 `experiments/`，Planning 评测结果会写入 `experiments/planning_eval_results.json`。

## 说明与边界

- 所有订单、商品、物流、余额均为 Mock 数据，定义在 `app/agent/tools/mock_data.py` 等文件中，不连接真实业务系统。
- 项目是命令行应用，未包含 Web 前端、鉴权、限流与生产级部署配置。
- `app/sessions/` 为运行时目录，已在 `.gitignore` 中排除；克隆后需重新构建知识库索引。
- Planning 目前只覆盖「订单是否发货 + 物流查询」这一类多步任务，工具白名单为 `query_order` 与 `query_logistics`。
- 敏感操作（如退款）在流程上要求先与用户确认，但仍建议在真实业务中叠加权限与人工审核。

## 许可证

本项目采用 [MIT License](LICENSE) 开源。

Copyright (c) 2026 2040643557