import { contextBridge } from 'electron'

contextBridge.exposeInMainWorld('offerPilotRuntime', {
  apiBaseUrl: process.env.OFFER_PILOT_API_BASE_URL || 'http://127.0.0.1:8080',
})
