import { defineConfig } from 'vite'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import electron from 'vite-plugin-electron/simple'
import react from '@vitejs/plugin-react'
import { createDevLauncher } from './scripts/dev-launcher.mjs'

const projectRoot = fileURLToPath(new URL('.', import.meta.url))
const devLauncher = createDevLauncher({ cwd: projectRoot })

// https://vitejs.dev/config/
export default defineConfig({
  root: projectRoot,
  publicDir: path.join(projectRoot, 'public'),
  build: {
    outDir: path.join(projectRoot, 'dist'),
    emptyOutDir: true,
  },
  plugins: [
    react(),
    {
      name: 'offerpilot-dev-lifecycle',
      apply: 'serve',
      closeBundle: () => devLauncher.close(),
    },
    electron({
      main: {
        // Shortcut of `build.lib.entry`.
        entry: path.join(projectRoot, 'electron/main.ts'),
        onstart: () => devLauncher.restart(),
      },
      preload: {
        // Shortcut of `build.rollupOptions.input`.
        // Preload scripts may contain Web assets, so use the `build.rollupOptions.input` instead `build.lib.entry`.
        input: path.join(projectRoot, 'electron/preload.ts'),
        async onstart({ reload }) {
          await devLauncher.ensureStarted()
          reload()
        },
      },
      // Ployfill the Electron and Node.js API for Renderer process.
      // If you want use Node.js in Renderer process, the `nodeIntegration` needs to be enabled in the Main process.
      // See 👉 https://github.com/electron-vite/vite-plugin-electron-renderer
      renderer: process.env.NODE_ENV === 'test'
        // https://github.com/electron-vite/vite-plugin-electron-renderer/issues/78#issuecomment-2053600808
        ? undefined
        : {},
    }),
  ],
})
