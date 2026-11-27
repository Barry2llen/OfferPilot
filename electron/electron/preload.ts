import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

// Only plain values and narrow wrapper functions cross the bridge; ipcRenderer itself is never exposed.
const windowControls = {
  minimize: () => ipcRenderer.send('window-controls:minimize'),
  toggleMaximize: () => ipcRenderer.send('window-controls:toggle-maximize'),
  close: () => ipcRenderer.send('window-controls:close'),
  isMaximized: () => ipcRenderer.invoke('window-controls:is-maximized') as Promise<boolean>,
  onMaximizedChange: (listener: (maximized: boolean) => void) => {
    const handler = (_event: IpcRendererEvent, maximized: unknown) => listener(Boolean(maximized))
    ipcRenderer.on('window-controls:maximized-changed', handler)
    return () => {
      ipcRenderer.removeListener('window-controls:maximized-changed', handler)
    }
  },
}

contextBridge.exposeInMainWorld('offerPilotRuntime', {
  apiBaseUrl: process.env.OFFER_PILOT_API_BASE_URL || 'http://127.0.0.1:8080',
  platform: process.platform,
  // macOS keeps its native traffic lights, so the renderer only draws buttons on Windows/Linux.
  ...(process.platform === 'darwin' ? {} : { windowControls }),
})
