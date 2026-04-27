<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# OfferPilot Frontend Agent Guide

## 基本要求

- 始终用中文回复用户。
- 修改代码前先阅读相关源码；涉及 Next.js 行为时，先查 `node_modules/next/dist/docs/` 中对应文档。本项目使用 `next@16.2.3`，不要按旧版 Next.js 经验直接改。
- 工作区可能已有用户改动；不要回退非本次任务产生的修改。

## 项目概览

- 技术栈：Next.js 16 App Router、React 19、TypeScript strict、Tailwind CSS v4。
- 入口和路由都在 `app/` 下，没有 `src/` 或 `pages/` 目录。
- `app/layout.tsx` 是服务端组件，负责 metadata、全局 CSS、`AppProvider`、`ToastProvider` 和 `AppShell`。
- 主要页面：
  - `app/page.tsx`：AI 对话页，使用 SSE 流式聊天。
  - `app/resumes/page.tsx`：简历列表、上传、删除。
  - `app/resumes/[id]/page.tsx`：简历详情、预览、替换、删除。
  - `app/settings/providers/page.tsx`：模型供应商配置。
  - `app/settings/selections/page.tsx`：模型选择配置。
- 共享代码：
  - `app/components/layout/`：全局外壳、侧边栏、上下文栏。
  - `app/components/ui/`：Button、Card、Badge、Toast、Drawer、Dialog、Spinner 等基础 UI。
  - `app/components/chat/`、`app/components/resumes/`、`app/components/settings/`：业务组件。
  - `app/lib/api/`：后端 REST/SSE API 封装和共享类型。
  - `app/lib/context/app-context.tsx`：当前模型选择、会话线程、Agent 状态、聊天历史刷新版本。
  - `app/hooks/`：`useAsyncData` 和 `useChatStream`。

## 开发命令

- 安装依赖：`npm install`
- 本地开发：`npm run dev`
- 代码检查：`npm run lint`
- 生产构建：`npm run build`

## Next.js / React 约定

- 默认保留服务端组件；只有用到 state、effect、事件处理、浏览器 API、React context 或自定义客户端 hook 时才加 `"use client"`。
- 不要把大范围布局无故改成客户端组件。客户端 Provider 可从服务端 `layout.tsx` 引入并包裹 `children`。
- App Router 文件约定按 Next 16 文档执行：`page.tsx` 暴露路由，`layout.tsx` 提供布局，`loading.tsx` 和 `error.tsx` 处理加载和错误边界。
- 动态路由如果使用服务端组件接收 `params`，先查 Next 16 文档；当前 `app/resumes/[id]/page.tsx` 是客户端组件，使用 `useParams()`。
- 使用 `@/*` 路径别名，指向项目根目录，例如 `@/app/lib/api/client`。

## API 与运行时配置

- 后端基础地址来自 `NEXT_PUBLIC_API_URL`，默认 `http://localhost:8080`。
- 浏览器运行时也支持 `window.offerPilotRuntime?.apiBaseUrl` 覆盖 API 地址。
- 所有普通 JSON 请求优先走 `apiRequest<T>()`；它会处理 base URL、JSON header、`FormData`、204 和 `ApiError`。
- 文件上传使用 `FormData`，不要手动设置 JSON `Content-Type`。
- SSE 聊天由 `aiChatApi.streamChat()` 和 `useChatStream()` 处理，事件类型包括 `thread`、`token`、`reasoning`、`tool_start`、`tool_end`、`tool_error`、`interrupt`、`final`、`error`。
- 新增后端字段或接口时，同步更新 `app/lib/api/types.ts` 和对应 API 模块。可参考根目录 `openapi.json`。

## 状态与交互模式

- 全局会话状态通过 `AppProvider` 管理；不要为当前线程、当前模型选择、Agent 状态再创建平行全局状态。
- 列表页常用 `useAsyncData(fetcher, deps)` 管理 loading/error/refetch。
- 操作成功或失败通过 `useToast()` 给反馈；确认删除走 `ConfirmDialog`。
- 表单抽屉使用 `FormDrawer`，提交期间用 `submitting`/`loading` 禁用按钮。
- 对话流式状态集中在 `useChatStream()`，不要在页面里重复实现 SSE 解析。

## UI 与样式

- Tailwind v4 token 定义在 `app/globals.css` 的 `@theme inline` 中，优先复用现有颜色、字体、阴影和语义 token。
- 基础按钮优先使用 `Button` 或 `buttonClassName()`；卡片、徽章、弹窗、抽屉、加载态优先使用 `app/components/ui/` 现有组件。
- 页面主体布局目前偏后台工具风格：`max-w-2xl`/`max-w-3xl` 内容区、紧凑标题、列表卡片、清晰 loading/error/empty 状态。新增页面保持一致。
- UI 文案以中文为主，匹配现有 OfferPilot 求职助手语境。

## 验证要求

- 改 TypeScript/React 代码后至少运行 `npm run lint`。
- 涉及路由、构建配置、Next 特性或服务端/客户端边界时，运行 `npm run build`。
- 仅改文档时不强制运行构建，但应检查 Markdown 内容和 git diff。
