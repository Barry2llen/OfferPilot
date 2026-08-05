# OfferPilot Frontend Agent Guide

## General requirements

- Read the relevant source, configuration, and project documentation before
  changing code.
- The worktree may contain user changes. Do not revert changes outside the
  current task.

## Project overview

- Stack: Vite, React 19, React Router, strict TypeScript, and Tailwind CSS v4.
- Static entry: `index.html`; React entry: `main.tsx`; routes:
  `app/router.tsx`.
- Files under `app/**/page.tsx` are ordinary React Router page components and
  are lazy-loaded with `React.lazy`.
- `app/components/layout/app-error-boundary.tsx` provides the global error
  boundary; `Suspense` provides route loading states.
- Main pages:
  - `app/page.tsx`: AI conversation with SSE streaming.
  - `app/resumes/page.tsx`: resume list, upload, and deletion.
  - `app/resumes/[id]/page.tsx`: resume details, preview, replacement, and
    deletion.
  - `app/job-descriptions/`: job-description analysis and details.
  - `app/files/page.tsx`: chat attachment library.
  - `app/settings/providers/page.tsx`: model provider and model selection
    configuration.
- Shared code:
  - `app/components/layout/`: application shell, sidebar, and context bar.
  - `app/components/ui/`: buttons, cards, badges, toasts, drawers, dialogs,
    spinners, and other primitives.
  - `app/components/chat/`, `app/components/resumes/`, and
    `app/components/settings/`: domain components.
  - `app/lib/api/`: REST/SSE API wrappers and shared types.
  - `app/lib/context/app-context.tsx`: model selection, thread, Agent state,
    chat history refresh, and global application state.
  - `app/hooks/`: `useAsyncData` and `useChatStream`.
  - `app/lib/i18n.ts`: `zh-CN` and `en-US` translation resources and
    locale selection.

## Development commands

- `npm install`: install dependencies.
- `npm run dev`: start the local Vite server.
- `npm run lint`: run ESLint.
- `npm run typecheck`: run the TypeScript compiler without emitting files.
- `npm run build`: create the production Vite build.

## React and routing conventions

- Use React Router's `Link`, `useNavigate`, `useLocation`, and
  `useParams`; do not introduce Next.js routing or components.
- Keep routes `/`, `/resumes`, `/resumes/:id`, `/files`,
  `/job-descriptions`, `/job-descriptions/:id`, and
  `/settings/providers`.
- `/settings` and `/settings/selections` redirect to
  `/settings/providers`.
- Use `React.lazy` and `Suspense` for page-level modules. Do not recreate
  route loading boundaries inside individual pages.
- Use the `@/*` path alias for imports from the project root.

## API and runtime configuration

- API URL precedence is
  `window.offerPilotRuntime.apiBaseUrl`, `VITE_API_URL`, then the current
  page's same-origin relative path.
- Without `VITE_API_URL`, the Vite server proxies through
  `VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8080`).
- Production is served by FastAPI from the same origin and uses relative API
  paths by default.
- Use `apiRequest<T>()` for ordinary JSON requests. It handles the base URL,
  JSON headers, `FormData`, 204 responses, locale headers, and `ApiError`.
- Use `FormData` for file uploads; do not set the JSON `Content-Type`
  manually.
- REST and SSE requests must send the active locale in `Accept-Language`.
  The backend returns localized known errors and matching
  `Content-Language`.
- SSE chat is handled by `aiChatApi.streamChat()` and
  `useChatStream()`. Event types include `thread`, `token`,
  `reasoning`, `tool_start`, `tool_end`, `tool_error`, `interrupt`,
  `final`, and `error`.
- When adding or changing backend fields or endpoints, update
  `app/lib/api/types.ts` and the corresponding API module.

## Internationalization

- All user-visible copy must use `i18next`/ `react-i18next`; do not add
  hardcoded UI text in a component.
- Keep both `zh-CN` and `en-US` resources in
  `app/lib/i18n.ts), with Simplified Chinese as the fallback.
- Initial locale precedence is persisted user choice, browser/system language,
  then `zh-CN`. The selected locale must remain persisted across reloads.
- Keep `document.documentElement.lang` and the page title synchronized with
  the active locale.
- Format dates, numbers, counts, labels, placeholders, validation messages,
  empty/loading/error states, modal text, and accessibility labels through the
  active locale.
- Do not translate AI responses, user input, resume or job-description source
  text, or persisted technical error details.

## State and interaction patterns

- Keep global thread, model selection, Agent state, and chat refresh state in
  `AppProvider`; do not create parallel global stores.
- Use `useAsyncData(fetcher, deps)` for list-page loading, error, and refresh
  state.
- Report successful and failed operations with `useToast()`; use
  `ConfirmDialog` for destructive confirmations.
- Use `FormDrawer` for forms and disable controls while submitting.
- Keep streaming state in `useChatStream()`; do not duplicate SSE parsing in
  page components.

## UI and styling

- Tailwind v4 tokens are defined in `app/globals.css`; prefer existing
  colors, fonts, shadows, and semantic tokens.
- Prefer `Button` or `buttonClassName()` for buttons. Reuse existing UI
  primitives for cards, badges, dialogs, drawers, loading, and empty states.
- The application uses a compact, readable operations-console style. New
  pages should preserve that visual language.
- Verify both locales when changing layout: translated text can be longer,
  and the language selector must remain usable on narrow screens.

## Validation

- After TypeScript/React changes, run `npm run lint` and
  `npm run typecheck`.
- For route, Vite, API-boundary, or rendering changes, run `npm run build`.
- For UI behavior changes, verify initial load, deep-route refresh, desktop
  and mobile layouts, language detection, manual switching, persistence,
  loading/error/empty states, and browser console errors.
- Documentation-only changes do not require a build, but Markdown content and
  the git diff must be checked.
