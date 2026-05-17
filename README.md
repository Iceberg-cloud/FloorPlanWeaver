# FloorPlanWeaver MVP

户型建筑平面多智能体交互设计平台（V1 Demo）。

## 功能闭环

- 用户自然语言输入需求
- Planner Agent 执行信息补全（追问）或输出最终方案
- Drawer Agent 根据最终方案直接调用图像模型出图
- 前端展示聊天、规划方案与户型图
- 支持重新规划、重新绘图

## 项目结构

```text
backend/   FastAPI + Pydantic + Orchestrator
frontend/  Next.js + TypeScript + Tailwind + Image Viewer
```

## 本地启动

### 1) 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2) 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认前端请求 `http://localhost:8000/api/v1`，可通过 `NEXT_PUBLIC_API_BASE` 覆盖。

## 核心 API

- `POST /api/v1/sessions`
- `POST /api/v1/chat`
- `POST /api/v1/plan/regenerate`
- `POST /api/v1/draft/regenerate`
- `GET /api/v1/sessions/{session_id}`

## 第二阶段接口预留（已完成）

后端已预留统一 LLM Provider 接口层：

- `backend/app/services/llm_client.py`
  - `ProviderAdapter`：统一协议
  - `MockProviderAdapter`：联调占位
  - `HttpCompatibleProviderAdapter`：真实 API 接入入口
- `backend/app/schemas/llm.py`
  - 标准请求/响应结构（消息、schema、超时重试元信息）
- `PlannerService` / `DrawerService`
  - 支持 `规则模式` 与 `LLM 模式` 自动回退

### 环境变量

```bash
LLM_PROVIDER=mock
LLM_API_BASE=
LLM_API_KEY=
LLM_MOCK_MODE=true
PLANNER_USE_LLM=false
DRAWER_USE_LLM=false
DRAWER_FALLBACK_TO_RULE=false
PLANNER_MODEL=planner-model
DRAWER_MODEL=drawer-model
LLM_TIMEOUT_SECONDS=45
LLM_MAX_RETRIES=2
```

### 你后续只需要做的事

1. 在 `HttpCompatibleProviderAdapter._call_provider_api()` 接入你的模型 API；
2. 配置 `LLM_PROVIDER/LLM_API_BASE/LLM_API_KEY`；
3. 打开开关：`PLANNER_USE_LLM=true`、`DRAWER_USE_LLM=true`；
4. 若你希望 Drawer 必须由图像模型出图，保持 `DRAWER_FALLBACK_TO_RULE=false`（推荐）；
5. 重启后端即可切换到真实模型。

### OpenAI 兼容接口说明（文本规划）

- `LLM_API_BASE` 支持两种写法：
  - `https://your-host/v1`
  - `https://your-host/v1/chat/completions`
- 适配器会自动拼接或直连 `/chat/completions`。
- 请求体已内置：
  - `messages`（system + user）
  - `response_format`（优先 `json_schema`，否则 `json_object`）
  - `temperature`

### OpenAI 兼容接口说明（图片生成）

- Drawer 会调用 `POST /v1/images/generations`（或你配置的等价 endpoint）。
- 请求体包含 `model`、`prompt`、`size`、`response_format=url`。
- 返回需包含 `data[0].url` 或 `data[0].b64_json`。

## 说明

当前 Planner/Drawer 为规则化可运行版本，用于先打通工程闭环。后续可在 `backend/app/services/llm_client.py` 接入真实大模型提供商，实现严格 JSON 结构化输出与重试超时策略。
