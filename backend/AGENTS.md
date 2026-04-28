# GLOBAL GUIDE

- ALWAYS REMEMBER TO ANSWER USER IN CHINESE

--- project-doc ---

# Repository Guidelines

## 项目结构与模块职责
仓库是 Python FastAPI 单体应用，入口是 `main.py`。`create_app()` 在生命周期内加载配置、初始化同步/异步数据库管理器、建表、创建 `DatabaseCheckpointer`，并装配带工具能力的 `SupervisorAgent`。

核心目录按职责拆分如下：

- `agent/`：Agent 相关代码。`agent/base.py` 定义基础图、状态、工作流和 interrupt/command 类型；`agent/graphs/model_call.py` 负责模型调用、工具调用、失败重试和 LangGraph interrupt；`agent/agents/supervisor/` 是当前对外 AI 服务使用的主 Agent；`agent/checkpointers/` 提供数据库检查点；`agent/models/` 负责聊天模型装载；`agent/tools/` 提供 Exa/MCP Web 搜索工具；`agent/workflows/` 保留业务工作流实现。
- `api/`：FastAPI 路由层。`api/routes/resume.py` 提供简历上传、替换、查询、删除和原文件预览；`api/routes/model_config.py` 提供模型供应商与模型选择 CRUD；`api/routes/ai.py` 提供同步 AI 对话和 SSE 流式对话，流式事件包括 token、工具事件、interrupt、final 和 error。
- `db/`：数据库层。`db/engine/` 管理同步/异步 SQLAlchemy 引擎与会话；`db/models/` 定义 ORM；`db/repositories/` 封装数据访问，包括模型配置、简历和 LangGraph checkpoint。
- `schemas/`：Pydantic 与 TypedDict 数据结构。`schemas/config/` 负责配置解析；`schemas/ai.py`、`schemas/command.py`、`schemas/model_provider.py`、`schemas/model_selection.py`、`schemas/resume_document.py` 等分别服务 API、Agent 和业务层。
- `services/`：业务服务层，当前包含简历文件处理、模型供应商服务和模型选择服务。API 层应通过 service/repository 访问业务与数据库，不直接写 ORM 逻辑。
- `exceptions/`：领域异常，按 agent、database、model、resume 等模块拆分。
- `utils/`：通用工具，包括日志、文档解析、流事件处理和乱码检测。
- `sql/`：数据库结构快照或初始化 SQL。修改表结构时需保持 SQLite/PostgreSQL 兼容。
- `tests/unit/`：单元测试；共享夹具放在 `tests/conftest.py`。
- `docs/`、`tasks/`：设计说明、技术文档和任务记录。
- `data/`、`logs/`、`dev/test-tmp/`：本地运行数据、日志和临时开发文件，不应放入业务逻辑依赖。

新增代码时保持层次清晰：配置解析不要混入服务逻辑，数据库访问不要泄漏到 API 或 Agent 节点，Agent 节点不要直接处理 HTTP 细节。

## 构建、测试与开发命令
统一使用 `uv` 管理依赖和执行命令，并始终在仓库根目录运行：

- `uv sync`：安装并锁定依赖。
- `uv run uvicorn main:app --reload`：启动本地 FastAPI 服务。
- `uv run pytest`：运行全部测试。
- `uv run pytest tests/unit/test_resume_api.py`：聚焦简历接口与 OpenAPI 文档。
- `uv run pytest tests/unit/test_model_config_api.py`：聚焦模型供应商/模型选择 CRUD 与文档。
- `uv run pytest tests/unit/test_ai_api.py`：聚焦 AI 同步/流式接口、SSE 事件、interrupt/retry 和工具事件。
- `uv run pytest tests/unit/test_model_call_graph.py`：聚焦 Agent 模型调用、工具调用、重试和异常分支。
- `uv run pytest tests/unit/test_database_engine.py tests/unit/test_database_checkpointer.py`：聚焦数据库引擎、建表和 LangGraph checkpoint。
- `uv run pytest tests/unit/test_chat_model.py`：聚焦模型装载错误封装。

如果修改了配置加载、数据库兼容性、模型装载逻辑、Agent 图、SSE 事件协议、接口文档或 SQL 文件，提交前至少运行对应定向测试。修改 `sql/*.sql` 时还应做跨数据库兼容校验。

## 编码风格与命名
目标 Python 版本为 `>=3.13`，默认要求完整类型标注。遵循 PEP 8，使用 4 空格缩进，模块/函数使用 `snake_case`，类使用 `PascalCase`。保持现有风格：

- Pydantic 使用 v2 风格校验器、`ConfigDict`、`Field(description=..., examples=...)`。
- SQLAlchemy 使用 2.x ORM 写法与显式 `Mapped` 标注。
- Agent 状态优先使用 `TypedDict`，节点函数保持单一职责。
- LangGraph interrupt 使用 `BaseInterupt` 作为对外中断负载，恢复执行使用 `schemas.command.BaseCommand` 与 `Command(resume=...)`。
- SSE 输出统一通过路由内 helper 做 JSON 安全转换，不直接拼接复杂对象。
- 工具能力通过 `agent.tools.get_all_tools(config)` 注入 `SupervisorAgent`；缺少 Exa Key 时应安全降级，不在导入阶段触发远程连接。
- 优先写小函数和早校验，避免把多层职责揉进一个模块。
- 文件系统路径优先使用 `Path`。
- FastAPI 路由应补齐 `summary`、`description`、`response_description` 与主要错误响应说明，保证 Swagger 文档可直接用于联调。
- 对外 schema 的公开字段必须补充 `Field(..., description=..., examples=...)`，避免 Swagger 中只出现裸字段名。

注释保持简洁，只解释非直观约束、状态流转或兼容性原因，不写重复代码字面的注释。

## API 与 Agent 行为约定
- `/resumes` 相关接口只处理文件型简历；旧文本简历接口已移除，不要恢复除非任务明确要求。
- `/model-providers` 与 `/model-selections` 是 AI 服务的模型配置来源。API Key 不应在响应中明文回显。
- `/ai/chat` 返回最终文本响应，并使用 `DatabaseCheckpointer` 按 `thread_id` 保存会话状态。
- `/ai/chat/stream` 返回 `text/event-stream`，应保持事件名稳定：`thread`、`token`、`tool_start`、`tool_end`、`tool_error`、`interrupt`、`final`、`error`。
- 流式失败重试依赖 LangGraph checkpoint：客户端收到 `interrupt` 后，必须用同一个 `thread_id` 发送 `command.type="retry"` 恢复执行。
- 修改 SSE 请求体、事件字段或重试语义时，必须同步更新 OpenAPI 描述和 `tests/unit/test_ai_api.py`。

## 测试约定
测试框架是 `pytest`。新测试文件命名为 `test_*.py`，放在 `tests/unit/` 下。修改以下能力时需要补充对应测试：

- 配置解析：覆盖根级 `database` / `web_search` 结构与兼容旧版 `offer_pilot.*` 结构。
- 数据库：同时考虑 SQLite 默认路径与 PostgreSQL 可选配置；PostgreSQL 相关测试依赖 `TEST_POSTGRES_*` 环境变量，缺失时允许跳过但不要删除。
- 数据表：覆盖 ORM 建表结果、关键列、唯一约束和外键行为；SQL 快照保持跨数据库兼容。
- Checkpoint：覆盖同步/异步 round trip、writes、复制删除和 prune。
- Agent 图：覆盖工具调用、工具错误隔离、模型调用重试、interrupt 恢复、异常分支与可调用模型选择器。
- 工具：覆盖有/无 Exa Key 时的工具装载行为，避免测试环境误连远程 MCP。
- 服务层：覆盖 schema 与 ORM 之间的双向转换及异常分支。
- API 层：覆盖成功响应、主要错误码，以及 `/openapi.json` 中的关键文档元数据。
- 文档解析与简历文件：覆盖 PDF、DOCX、图片 OCR、预览转换、依赖缺失和不支持格式。

## 配置与安全
不要提交真实密钥到 `config.yaml`、`.env` 或示例文件。默认配置模板使用 `config.example.yaml`。

当前配置项包括：

- `database`：默认 SQLite，路径为 `./data/offer_pilot.db`；可切换 PostgreSQL。
- `resume_upload_dir`：默认 `./data/resumes`。
- `model_call_retry_attempts`：模型调用失败时的内部重试次数。
- `web_search`：Exa 搜索类型、返回内容长度和 guiding query。
- `exa_api_key`：存在时启用 Exa Web 搜索工具；缺失时默认禁用工具并记录 warning。
- `debug`：控制调试日志行为。

如果接口行为、配置格式、数据库结构或模型接入方式发生变化，需要同步更新 `config.example.yaml`、Swagger/OpenAPI 描述、测试断言和必要文档。

## 提交与合并请求
提交信息延续当前历史风格，使用 `<type>:<中文摘要>`，例如 `feat:补充模型选择服务测试`、`fix:修正模型提供商映射`。一次提交只做一件事，避免把重构、功能和文档混在一起。

Pull Request 描述至少说明：

- 变更目的
- 影响模块
- 测试结果
- 是否涉及配置、数据库结构、接口协议或模型接入方式调整

如果接口行为、请求体、响应结构、SSE 事件、配置格式或数据表结构发生变化，需要附上示例或迁移说明。
