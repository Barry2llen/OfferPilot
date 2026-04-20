# Repository Guidelines

## 项目结构与模块职责
仓库当前以 Python 单体应用为主，入口是 `main.py`，负责创建 FastAPI 应用并在生命周期内初始化数据库。核心目录按职责拆分如下：

- `agent/`：Agent 相关代码，包含输入校验、状态定义、图编排、模型装载与工作流占位实现。
- `api/`：FastAPI 路由层，当前主要由 `api/routes/resume.py` 提供简历文件管理与原文件预览接口。
- `db/`：数据库层，`db/engine/` 管理引擎与会话，`db/models/` 定义 ORM，`db/repositories/` 封装数据访问。
- `schemas/`：Pydantic 数据结构，`schemas/config/` 负责配置解析，其余 schema 用于服务层、接口层与 Agent 层输入输出。
- `services/`：面向业务的服务封装，当前包含简历文件处理、模型提供商与模型选择服务。
- `utils/`：通用工具，当前包含日志封装。
- `sql/`：数据库结构快照或初始化 SQL。
- `data/`：SQLite 文件等本地运行数据。
- `tests/unit/`：单元测试；共享夹具放在 `tests/conftest.py`。
- `docs/`：设计说明与技术文档。

新增代码时优先保持这一层次：配置解析不要混入服务逻辑，数据库访问不要直接泄漏到 API 或 Agent 节点。

## 构建、测试与开发命令
统一使用 `uv` 管理依赖和执行命令，并始终在仓库根目录运行：

- `uv sync`：安装并锁定依赖。
- `uv run uvicorn main:app --reload`：启动本地 FastAPI 服务。
- `uv run pytest`：运行全部测试。
- `uv run pytest tests/unit/test_resume_api.py`：聚焦简历接口与 OpenAPI 文档。
- `uv run pytest tests/unit/test_model_call_graph.py`：聚焦 Agent 图逻辑。
- `uv run pytest tests/unit/test_database_engine.py`：聚焦数据库引擎与建表逻辑。

如果修改了配置加载、数据库兼容性、模型装载逻辑或 FastAPI 接口文档，提交前至少运行对应的定向测试。

## 编码风格与命名
目标 Python 版本为 `>=3.13`，默认要求完整类型标注。遵循 PEP 8，使用 4 空格缩进，模块/函数使用 `snake_case`，类使用 `PascalCase`。保持现有风格：

- Pydantic 使用 v2 风格校验器与类型定义。
- SQLAlchemy 使用 2.x ORM 写法与显式 `Mapped` 标注。
- Agent 状态优先使用 `TypedDict`，节点函数保持单一职责。
- 优先写小函数和早校验，避免把多层职责揉进一个模块。
- 文件系统路径优先使用 `Path`。
- FastAPI 路由应补齐 `summary`、`description`、`response_description` 与主要错误响应说明，保证 Swagger 文档可直接用于联调。
- 对外 schema 的公开字段应优先补 `Field(..., description=..., examples=...)`，避免 Swagger 中只出现裸字段名。

注释保持简洁，只解释非直观约束、状态流转或兼容性原因，不写重复代码字面的注释。

## 测试约定
测试框架是 `pytest`。新测试文件命名为 `test_*.py`，放在 `tests/unit/` 下。修改以下能力时需要补充对应测试：

- 配置解析：覆盖根级 `database` 结构与兼容旧版 `offer_pilot.database` 结构。
- 数据库：同时考虑 SQLite 默认路径与 PostgreSQL 可选配置。
- Agent 图：覆盖工具调用、重试、异常分支与可调用模型选择器。
- 服务层：覆盖 schema 与 ORM 之间的双向转换及异常分支。
- API 层：覆盖成功响应、主要错误码，以及 `/openapi.json` 中的关键文档元数据。

PostgreSQL 相关测试依赖 `TEST_POSTGRES_*` 环境变量；缺失时允许跳过，但不要删除这类兼容性测试。

## 提交与合并请求
提交信息延续当前历史风格，使用 `<type>:<中文摘要>`，例如 `feat:补充模型选择服务测试`、`fix:修正模型提供商映射`。一次提交只做一件事，避免把重构、功能和文档混在一起。

Pull Request 描述至少说明：

- 变更目的
- 影响模块
- 测试结果
- 是否涉及配置、数据库结构或模型接入方式调整

如果接口行为、配置格式或数据表结构发生变化，需要附上示例或迁移说明。
如果改动了接口说明、请求体或响应结构，需同步更新 Swagger/OpenAPI 描述与对应测试断言。

## 配置与安全
不要提交真实密钥到 `config.yaml` 或其他示例文件。默认配置模板使用 `config.example.yaml`，模型提供商的 `api_key`、第三方 `base_url` 等敏感信息只应出现在本地环境或受控部署配置中。

当前数据库默认使用 SQLite，本地文件路径为 `./data/offer_pilot.db`；如果切换到 PostgreSQL，确保在文档或 PR 中同步说明新增字段与依赖。任何会影响启动行为的配置项，都应在示例配置与测试中一并更新。
