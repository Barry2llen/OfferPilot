# OfferPilot Frontend Agent Guide

## 基本要求

- 始终用中文回复用户。
- 修改代码前先阅读相关源码、配置和项目文档。
- 工作区可能已有用户改动；不要回退非本次任务产生的修改。

## 项目概览

- 技术栈：Vite、React 19、React Router、TypeScript strict、Tailwind CSS v4。
- 静态入口是 `index.html`，React 入口是 `main.tsx`，路由集中在 `app/router.tsx`。
- `app/**/page.tsx` 是普通 React 页面组件，按 React Router 路由通过 `React.lazy` 加载。
- `app/components/layout/app-error-boundary.tsx` 提供全局错误边界，`Suspense` 提供路由加载态。
- 主要页面：
  - `app/page.tsx`：AI 对话页，使用 SSE 流式聊天。
  - `app/resumes/page.tsx`：简历列表、上传、删除。
  - `app/resumes/[id]/page.tsx`：简历详情、预览、替换、删除。
  - `app/job-descriptions/`：职位描述分析和详情。
  - `app/files/page.tsx`：聊天附件文件库。
  - `app/settings/providers/page.tsx`：模型供应商和模型选择配置。
- 共享代码：
  - `app/components/layout/`：全局外壳、侧边栏和上下文栏。
  - `app/components/ui/`：Button、Card、Badge、Toast、Drawer、Dialog、Spinner 等基础 UI。
  - `app/components/chat/`、`app/components/resumes/`、`app/components/settings/`：业务组件。
  - `app/lib/api/`：后端 REST/SSE API 封装和共享类型。
  - `app/lib/context/app-context.tsx`：当前模型选择、会话线程、Agent 状态、聊天历史刷新版本。
  - `app/hooks/`：`useAsyncData` 和 `useChatStream`。

## 开发命令

- 安装依赖：`npm install`
- 本地开发：`npm run dev`
- 代码检查：`npm run lint`
- 类型检查：`npm run typecheck`
- 生产构建：`npm run build`

## React 与路由约定

- 使用 React Router 的 `Link`、`useNavigate`、`useLocation` 和 `useParams`，不要引入 Next 路由或 Next 专用组件。
- 路由保持 `/`、`/resumes`、`/resumes/:id`、`/files`、`/job-descriptions`、`/job-descriptions/:id` 和 `/settings/providers`。
- `/settings` 与 `/settings/selections` 必须重定向到 `/settings/providers`。
- 页面级模块使用 `React.lazy` 与 `Suspense`，不要在页面中重复实现路由加载边界。
- 使用 `@/*` 路径别名，指向项目根目录，例如 `@/app/lib/api/client`。

## API 与运行时配置

- API 地址优先级固定为 `window.offerPilotRuntime.apiBaseUrl`、`VITE_API_URL`、当前页面同源相对路径。
- 未配置 `VITE_API_URL` 时，Vite 开发服务器通过 `VITE_API_PROXY_TARGET`（默认 `http://127.0.0.1:8080`）代理后端 API。
- 生产构建由 FastAPI 在同一 origin 托管，默认使用相对 API 路径。
- 所有普通 JSON 请求优先走 `apiRequest<T>()`；它会处理 base URL、JSON header、`FormData`、204 和 `ApiError`。
- 文件上传使用 `FormData`，不要手动设置 JSON `Content-Type`。
- SSE 聊天由 `aiChatApi.streamChat()` 和 `useChatStream()` 处理，事件类型包括 `thread`、`token`、`reasoning`、`tool_start`、`tool_end`、`tool_error`、`interrupt`、`final`、`error`。
- 新增后端字段或接口时，同步更新 `app/lib/api/types.ts` 和对应 API 模块。

## 状态与交互模式

- 全局会话状态通过 `AppProvider` 管理；不要为当前线程、当前模型选择、Agent 状态再创建平行全局状态。
- 列表页常用 `useAsyncData(fetcher, deps)` 管理 loading/error/refetch。
- 操作成功或失败通过 `useToast()` 给反馈；确认删除走 `ConfirmDialog`。
- 表单抽屉使用 `FormDrawer`，提交期间用 `submitting`/`loading` 禁用按钮。
- 对话流式状态集中在 `useChatStream()`，不要在页面里重复实现 SSE 解析。

## UI 与样式

- Tailwind v4 token 定义在 `app/globals.css` 的 `@theme inline` 中，优先复用现有颜色、字体、阴影和语义 token。
- 基础按钮优先使用 `Button` 或 `buttonClassName()`；卡片、徽章、弹窗、抽屉、加载态优先使用 `app/components/ui/` 现有组件。
- 页面主体布局目前偏后台工具风格：紧凑标题、列表卡片、清晰 loading/error/empty 状态。新增页面保持一致。
- UI 文案以中文为主，匹配现有 OfferPilot 求职助手语境。

## 验证要求

- 改 TypeScript/React 代码后至少运行 `npm run lint` 和 `npm run typecheck`。
- 涉及路由、Vite 构建配置或 API 运行时边界时，运行 `npm run build`。
- 修改渲染行为后，通过本地浏览器验证首屏、深层路由刷新、移动端布局和控制台错误。
- 仅改文档时不强制运行构建，但应检查 Markdown 内容和 git diff。
