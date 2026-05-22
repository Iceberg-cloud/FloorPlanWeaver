# FloorPlanWeaver

**多智能体户型平面交互设计平台** — 用自然语言描述需求，由规划师、布局顾问与设计师协作，生成可执行的户型方案与平面图。

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.1+-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Next.js-14-000?style=flat-square&logo=next.js&logoColor=white" alt="Next.js" />
  <img src="https://img.shields.io/badge/Tests-131_passing-brightgreen?style=flat-square" alt="Tests" />
  <img src="https://img.shields.io/badge/License-MVP-demo-slate?style=flat-square" alt="License" />
</p>

---

## 功能概览

| 模块 | 角色 | 能力 |
|------|------|------|
| **Planner** | 规划师 | 最多追问 1～2 轮后出方案并出图；输出房间清单、面积与动线 |
| **Layout** | 布局顾问 + 工程师 | LLM 仅输出语义约束 → 网格 beam search 布置 → 规则校验填满轮廓（非 LLM 直接画几何） |
| **Drawer** | 设计师 | 根据最终方案生成多模态户型效果图（可选，纯图形无文字） |

前端提供：

- 需求对话与快捷模板（点击填入输入框，确认后发送）
- **外轮廓面积优先**：已保存外轮廓时，口述建筑面积与轮廓不一致则以轮廓为准，并提示先绘制外轮廓
- **多环节思考进度**（规划师 / 布局顾问 / 布局工程师 / 设计师）
- **正交外轮廓编辑器**（网格吸附、点击闭合、顶点拖拽）
- 规划方案预览、矢量 / 多模态双视图
- SVG 自适应字体渲染（前端直接渲染，中文字体完美显示）
- **可折叠对话历史**（超过 8 条自动折叠，保留最近 5 条，支持滚轮滚动）

---

## 环境配置（从零开始）

以下步骤假设你尚未安装本项目运行环境。完成后**优先使用项目根目录的 `run.py` 启动**（见「启动项目」）；仅在调试时才分终端手动启动。

### 0. 前置软件

| 软件 | 版本要求 | 用途 |
|------|----------|------|
| [Python](https://www.python.org/downloads/) | **3.10 或以上**（建议 3.10 / 3.11） | 后端、测试、`run.py` |
| [Node.js](https://nodejs.org/) | **18 LTS 或以上**（自带 npm） | 前端 Next.js |
| Git（可选） | 任意较新版本 | 克隆仓库 |

安装 Python 后请确认命令可用：

```bash
python --version    # 或 Windows 上 py -3.10 --version
node --version
npm --version
```

> **Windows 提示**：安装 Python 时勾选 "Add python.exe to PATH"。若 `python` 不可用，可尝试 `py -3.10`。

### 1. 获取项目代码

```bash
git clone <你的仓库地址> FloorPlanWeaver
cd FloorPlanWeaver
```

若已是压缩包，解压后进入项目根目录（包含 `run.py`、`backend`、`frontend` 的目录）。

### 2. 创建 Python 环境并安装后端依赖

任选 **A（venv，推荐）** 或 **B（Conda）**，不要混用两套环境。

#### 方式 A：venv（Windows / macOS / Linux 通用）

在项目根目录执行：

```bash
# 创建虚拟环境（目录名 .venv 可自定）
python -m venv .venv

# 激活（每次新开终端都要先激活）
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Windows CMD:
.\.venv\Scripts\activate.bat
# macOS / Linux:
source .venv/bin/activate

# 升级 pip 并安装后端依赖
pip install --upgrade pip
pip install -r backend/requirements.txt
```

#### 方式 B：Conda / Miniconda

```bash
conda create -n floorplanweaver python=3.10 -y
conda activate floorplanweaver
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 3. 配置后端环境变量 `.env`

```bash
cd backend
```

复制模板（Windows PowerShell 用 `copy`，macOS/Linux 用 `cp`）：

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

用文本编辑器打开 `backend/.env`，至少配置 LLM 网关（否则需将 `LLM_MOCK_MODE=true` 用于本地无密钥调试）：

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_PROVIDER` | 兼容 OpenAI 的网关 | `openai` |
| `LLM_API_BASE` | API 根地址 | `https://your-gateway/v1` |
| `LLM_API_KEY` | 密钥（勿提交到 Git） | `sk-...` |
| `LLM_MOCK_MODE` | 无密钥时走 mock | `false` |
| `PLANNER_USE_LLM` | 规划师是否调 LLM | `true` |
| `DRAWER_USE_LLM` | 设计师是否调多模态 | `true` |
| `DRAWER_FALLBACK_TO_RULE` | 出图失败时规则兜底 | `true` |
| `PLANNER_MODEL` / `DRAWER_MODEL` | 模型名 | 见 `.env.example` |
| `LAYOUT_USE_GRID_COMPILER` | 方案 A 网格 beam search | `true` |
| `PLANNER_MAX_ASK_ROUNDS` | 最多追问轮数（1=追问一次后出图） | `1` |
| `SESSION_STORE` | 会话存储 | `sqlite` |
| `SESSION_DB_PATH` | SQLite 路径 | `backend/data/sessions.db` |

完整列表见 [`backend/.env.example`](backend/.env.example)。配置完成后回到项目根目录：`cd ..`。

### 4. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

（可选）后端不在本机 `8000` 端口时，在 `frontend` 下新建 `.env.local`：

```ini
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000/api/v1
```

### 5. 自检（确认环境正确）

**先激活** 第 2 步中的 Python 虚拟环境，再执行：

```bash
cd backend
python -m pytest tests/ -q
cd ../frontend
npx tsc --noEmit
cd ..
```

无报错即表示 Python 依赖与前端类型检查通过。

---

## 启动项目

完成「环境配置」后启动应用。**请优先使用 `run.py`**：一条命令拉起后端与前端并打开浏览器。分终端手动启动仅用于单独调试某一端。

### 推荐：`run.py`（默认）

在**已激活 Python 环境**的前提下，于**项目根目录**执行：

```bash
python run.py
```

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:3001 |
| 后端 API | http://localhost:8000 |
| 健康检查 | http://localhost:8000/api/v1/health |

说明：

- `run.py` 使用**当前终端里的 `python`**（即你激活的 venv / conda）；需已执行 `pip install -r backend/requirements.txt` 与 `cd frontend && npm install`。
- Windows 下脚本会尝试释放被占用的 **8000 / 3001** 端口。
- 仓库内若配置了 `PREFERRED_PYTHON` 且路径存在，会优先使用该解释器；新用户一般只需 `python run.py`。

### 备选：手动分终端启动

仅在需要分别调试后端/前端、或不用 `run.py` 时使用。环境变量与依赖安装要求与上文相同。

**终端 1 — 后端**

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**终端 2 — 前端**

```bash
cd frontend
npm run dev
```

默认前端请求 `http://localhost:8000/api/v1`；端口或主机不同时，在 `frontend/.env.local` 设置 `NEXT_PUBLIC_API_BASE`。

---

## 项目结构

```
FloorPlanWeaver/
├── run.py                 # 推荐：同时启动前后端
├── backend/
│   ├── app/
│   │   ├── agents/        # Planner / Layout / Drawer 提示与解析
│   │   ├── api/           # FastAPI 路由
│   │   ├── orchestrator/  # 会话工作流编排
│   │   ├── renderers/     # SVG 渲染器（自适应字体 + 精确标签定位）
│   │   ├── schemas/       # Pydantic 模型
│   │   └── services/      # 规划、布局编译、后处理、LLM 客户端、记忆管理
│   └── tests/             # pytest（131 个测试用例）
└── frontend/
    ├── app/               # Next.js 页面
    ├── components/        # 对话、轮廓编辑器、方案、平面图、思考流水线 UI
    └── lib/               # API、布局/规划归一化、多边形渲染、流水线阶段定义
```

---

## 多智能体流水线

```mermaid
flowchart LR
    U[用户对话] --> P[规划师 Planner]
    P -->|信息不足| Q[追问补全]
    P -->|FINAL_PLAN| L[布局顾问 Semantic LLM]
    L --> C[网格 Beam Search 编译]
    C --> R[自动修复 + 面积校正]
    R --> F[100% 轮廓填充]
    F --> V[矢量 SVG]
    P --> D[设计师 Drawer]
    D --> I[户型效果图]
```

### 矢量布局（方法 A — Grid Search）

1. **语义层**：LLM 输出 `center_x/y`、`width_ratio/height_ratio` 等归一化位置与大小（非绝对坐标）
2. **约束合并**：将 Planner 邻接图（`adjacency_graph`）与语义层邻接意图合并，厨房→餐厅为硬邻接约束
3. **网格搜索层**：0.25m 精度网格，Beam Search（宽度 16）+ 贪心回退放置所有房间；餐厅先于厨房放置以保证邻接
4. **自动修复**：面积双向校正、矩形化强制（卫生间/卧室/阳台保证轴对齐矩形且不超目标 135%）、碎片吸收、灵活房间补偿、断开区域愈合
5. **100% 轮廓填充**：迭代 `fill → compact → heal` 循环，确保外轮廓内无空白区域
6. **几何校验**：覆盖率、无重叠、无间隙、连通性、矩形约束、边界贴合、邻接关系
7. **多边形导出**：硬矩形房间用 4 点 bbox、弹性房间（客厅/餐厅/书房）用 boundary polygonization

### 房间矩形保证

以下房间类型强制输出为轴对齐矩形且面积不超过目标 135%：**卫生间、主卧、次卧、卧室、阳台**。通过 `_compact_to_solid_rect`（限制最大面积的内接矩形搜索）实现。厨房可为矩形或 L 形。

### 放置优先级

房间按以下顺序放置，确保邻接关系：

1. 卫生间 / 阳台 / 卧室（贴边、硬矩形）
2. **餐厅**（有厨房时先进 strong 分区，确保厨房可贴邻放置）
3. 厨房（贴餐厅，评分中厨房-餐厅邻接权重 ×3）
4. 书房
5. 客厅 / 客餐厅（填充剩余最大连续区域）

### 绘图方式

| 模式 | 说明 |
|------|------|
| `vector` | 仅矢量布局（方法 A） |
| `multimodal` | 仅多模态出图（方法 B，纯图形无文字） |
| `both` | 同时生成 A + B |

---

## 跨轮记忆与偏好系统

平台支持**跨轮对话记忆**，用户在对话中提到的偏好和需求会被自动提取并持续保留：

### 工作记忆架构

| 组件 | 功能 |
|------|------|
| `collected_requirements` | 结构化工作记忆（户型、面积、朝向、房间清单） |
| `user_preferences` | 软偏好列表（有老人、有宠物、干湿分离、主卧要大等） |
| `conversation_summary` | 最近对话摘要，供 LLM 上下文参考 |
| `apply_delta_to_memory()` | 从当前消息 + 历史消息中提取并合并偏好 |
| `merge_snapshot()` | 去重合并新信息到持久化记忆 |

### 支持的偏好模式（22 种）

- **居住者**：有老人居住、有小孩、有宠物
- **空间要求**：主卧要宽敞、客厅要大、厨房要大、需要书房、需要衣帽间、需要玄关
- **设计偏好**：干湿分离、动静分离、南北通透、采光充足、通风良好、无障碍设计
- **特殊设施**：厨房要放岛台、步入式衣柜、居家办公区、主卧带独卫

### 修改意图检测

系统能识别用户的修改指令（如"请将厨房移动至右下角"），不会覆盖已有的房间列表，而是：
- 保留所有已提取的房间信息
- 提取位置约束注入到对应房间的 `notes`（如"用户要求：右下角"）
- 位置约束通过 `_extract_prefer_edge` 转换为布局引擎用的 edge 标签

### 复合房间名匹配

房间提取支持**复合名优先匹配**和**位置去重**：
- "客餐厅一体" → 匹配为 `客餐厅`（22㎡），不会额外匹配 `客厅` 和 `餐厅`
- "卧室" → 匹配为 `卧室`（14㎡），与 `主卧`/`次卧` 并列
- "客餐厅"、"起居室" 等不在标准模板中的类型也能正确处理

### 多轮对话示例

```
用户: 我要三居室住宅          → 提取 layout_type=三居, building_type=住宅
用户: 120平，有老人和小孩     → 提取 target_area=120, preferences=[有老人, 有小孩]
用户: 主卧要大，需要书房，南向 → 提取 orientation=南向, preferences+=[主卧宽敞, 需要书房]
                                     ↑ 之前轮次的偏好仍保留
```

所有偏好会融入规划师的 `design_goals`、`drawing_brief` 和 `lifestyle_tags`。

---

## 外轮廓编辑器

前端提供功能完善的 SVG 正交外轮廓编辑器：

| 功能 | 说明 |
|------|------|
| 正交绘制 | 线段自动吸附为水平/垂直，保证所有角为直角 |
| 网格吸附 | 所有坐标吸附到 0.25m 网格，与后端布局引擎精度一致 |
| 点击闭合 | 绘制 3 个以上顶点后，靠近起点点击即可闭合多边形 |
| 顶点拖拽 | 切换到"选择"工具可拖拽任意顶点调整外轮廓 |
| 预设模板 | 矩形 80/100/120/140㎡、L 形 100㎡、T 形 120㎡ |
| 自定义尺寸 | 输入宽×高直接生成矩形轮廓 |
| 边长标注 | 每条边显示精确长度（0.01m 精度） |
| 直角标记 | 正交模式下显示直角符号 |
| 撤销/清空 | 支持撤销最后一个顶点和清空所有顶点 |
| 缩放/平移 | 滚轮缩放，Shift+拖拽平移 |

---

## SVG 渲染

前端使用 React SVG 直接渲染布局，确保中文完美显示：

- **自适应字体**：根据房间面积分 4 档字体大小（≥14㎡/≥8㎡/≥4㎡/<4㎡），小于 3㎡ 的房间只显示名称
- **精确标签定位**：`polygonLabelCenter` 算法确保标签始终在房间内部，不重叠
- **动态 viewBox**：自动计算所有顶点范围，添加 padding 确保不裁剪
- **clipPath 裁剪**：房间名称不超过房间边界，长名自动截断
- **中文完美支持**：使用系统字体栈（Microsoft YaHei / PingFang SC / Noto Sans SC）
- **多模态绘图无文字**：方法 B 出图提示词明确禁止任何文字标注，仅以颜色分区和墙体线条表达

---

## 前端：思考进度 UI

请求进行中时，对话区会展示**多智能体协作**时间线，顶部状态栏同步当前环节，例如：

- 规划师思考中
- 布局顾问分析中
- 布局工程师编译中
- 布局优化中
- 设计师绘图中

环节列表随「绘图方式」自动增减；完成后状态栏显示各 Agent 执行摘要。

---

## 测试

在已激活的 Python 环境中：

```bash
cd backend
python -m pytest tests/ -q
```

```bash
cd frontend
npx tsc --noEmit
```

131 个后端测试覆盖：
- 跨轮记忆与偏好提取（`test_cross_turn_memory.py`，13 个用例）
- 修改意图检测与位置约束（`test_modification_memory.py`，16 个用例）
- 房间提取边界场景（`test_room_extraction.py`，6 个用例）
- 记忆合并与快照（`test_requirement_memory.py`）
- 规划师多轮对话（`test_planner_memory_flow.py`）
- **网格搜索几何正确性**（`test_grid_geometry.py`，22 个用例）：覆盖率、无间隙、连通性、矩形约束、厨房邻接餐厅
- **9 房间完整布局覆盖**（`test_vector_layout_coverage.py`，6 个用例）
- **硬矩形房间强制实心**（`test_rect_enforcement.py`，10 个用例）
- **客厅面积接近目标**（`test_living_room_area.py`，4 个用例）
- **多边形导出无重叠**（`test_polygon_export_overlap.py`）
- **网格搜索布局**（`test_grid_search_layout.py`）：优先级顺序、邻接图合并、厨房-餐厅 must 邻接
- 语义布局编译（`test_semantic_layout.py`）
- API 集成全链路（`test_chat_integration.py`）
- SVG 绘制提示词（`test_drawer_prompt.py`）
- 外轮廓面积优先（`test_outline_area_priority.py`）
- 会话清理（`test_session_cleanup.py`）

---

## 常见问题

**Q: 界面提示 `PlannerAskForMore` 校验错误？**
A: 已在后端对 LLM 残缺 JSON 做补全与回退。请**完全重启** `python run.py`（推荐）；若用手动启动则重启对应 uvicorn 进程，避免旧代码未加载。

**Q: 端口被占用？**
A: 优先重新执行 `python run.py`，脚本会自动尝试释放 8000/3001；仍占用时可 `netstat` + `taskkill`（Windows）或结束对应进程。

**Q: 矢量图房间数为 0 或报错？**
A: 前端已用 `normalizeLayout()` 适配后端嵌套 `layout.layout.rooms` 结构，请拉取最新前端代码。

**Q: 房间超出轮廓或有间隙？**
A: 网格搜索编译器（`compile_method=grid_search`）已确保几何正确性：房间不超出外轮廓、内部紧密贴合、关键房间强制矩形。后处理跳过 `grid_search` 结果以保持精度。

**Q: 卫生间/卧室/阳台不是矩形？**
A: `_compact_to_solid_rect`（限制面积上限的内接矩形搜索）强制上述房间为轴对齐实心矩形，面积不超过目标 135%。

**Q: 轮廓内有空白未分配区域？**
A: 已通过迭代 `fill → compact → heal` 循环确保 100% 轮廓填充。客厅等弹性房间会吸收所有剩余空间。

**Q: 厨房没有与餐厅相邻？**
A: 厨房-餐厅邻接为硬约束（`must`）：餐厅先于厨房放置，厨房评分中邻接餐厅权重 ×3，默认语义布局中厨房-餐厅为 `must` 邻接。

**Q: 提示 `LLM 调用失败: The read operation timed out`？**
A: 模型响应慢，默认硬限制 120s（`LLM_HARD_TIMEOUT_SECONDS`）。请重启后端重试；仍慢可换 `*-Flash` 模型或检查 `LLM_API_BASE` 网络。

**Q: 多轮对话还要重复说面积/户型？**
A: 已启用**跨轮工作记忆**：同一会话内自动合并 `collected_requirements` 与 `user_preferences`，规划师 LLM 接收最近 8 轮对话 + 需求快照 + 用户偏好 + 对话摘要。

**Q: 之前说的偏好（如"有老人"）会被记住吗？**
A: 会。`apply_delta_to_memory()` 会扫描最近 6 条历史消息提取偏好，并通过 `merge_snapshot()` 去重合并到持久化记忆中，无需重复说明。

**Q: 修改需求（如"把厨房移到右下角"）会丢失之前的房间信息吗？**
A: 不会。系统会检测修改意图，保留所有已提取的房间，只注入位置约束。修改指令不会覆盖 `room_program`。

**Q: SVG 中文显示为方块或空白？**
A: 已修复。前端使用 React SVG 直接渲染（非内嵌 base64），使用系统字体栈（Microsoft YaHei / PingFang SC / Noto Sans SC），中文完美显示。

**Q: 房间名称超出房间边界？**
A: 已修复。前端使用 `clipPath` 裁剪房间名称，长名自动截断，确保文字不溢出房间区域。

**Q: 规划师漏掉了卧室等房间？**
A: 已修复。房间提取支持"卧室"（14㎡）、"客餐厅"（22㎡）等复合名，复合名优先匹配避免重复。例如"一室一厅，需要卧室、客餐厅一体"会正确提取 5 个房间。

**Q: 关闭后对话还会保留吗？**
A: 关闭页面（`pagehide`）或点击「关闭服务」时，会调用 `/sessions/{id}/end` 删除服务端会话（含全部消息与方案），并清除浏览器 `localStorage` 中的 sessionId。下次打开为全新会话。

---

## 技术栈

- **后端**：FastAPI · Pydantic v2 · 自研网格 Beam Search 布局编译器 · OpenAI 兼容 LLM 网关 · 跨轮记忆系统 · 修改意图检测 · 邻接约束合并
- **前端**：Next.js 14 · React · TypeScript · Tailwind CSS · SVG 正交轮廓编辑器 · 自适应字体渲染 · clipPath 文字裁剪

---

## 许可证

MVP 演示项目，仅供学习与内部验证使用。
