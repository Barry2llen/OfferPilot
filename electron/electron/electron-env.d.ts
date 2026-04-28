/// <reference types="vite-plugin-electron/electron-env" />

declare namespace NodeJS {
  interface ProcessEnv {
    /**
     * The built directory structure
     *
     * ```tree
     * ├─┬─┬ dist
     * │ │ └── index.html
     * │ │
     * │ ├─┬ dist-electron
     * │ │ ├── main.js
     * │ │ └── preload.js
     * │
     * ```
     */
    APP_ROOT?: string
    /** /dist/ or /public/ */
    VITE_PUBLIC?: string
    OFFER_PILOT_API_BASE_URL?: string
    OFFER_PILOT_APP_URL?: string
    OFFER_PILOT_BACKEND_DIR?: string
    OFFER_PILOT_FRONTEND_DIR?: string
  }
}

// Used in Renderer process, expose in `preload.ts`
interface Window {
  offerPilotRuntime?: {
    apiBaseUrl?: string
  }
}
