/** Window controls bridged from Electron preload on Windows/Linux; absent in browsers and on macOS. */
export interface WindowControlsBridge {
  minimize: () => void;
  toggleMaximize: () => void;
  close: () => void;
  isMaximized: () => Promise<boolean>;
  onMaximizedChange: (listener: (maximized: boolean) => void) => () => void;
}

/** Runtime bridge injected by `electron/electron/preload.ts`. */
export interface OfferPilotRuntime {
  apiBaseUrl?: string;
  platform?: string;
  windowControls?: WindowControlsBridge;
}

declare global {
  interface Window {
    offerPilotRuntime?: OfferPilotRuntime;
  }
}

export function getWindowControls(): WindowControlsBridge | null {
  if (typeof window === "undefined") return null;
  return window.offerPilotRuntime?.windowControls ?? null;
}

// One bridge subscription shared by every mounted WindowControls (app shell plus each dialog).
let maximized = false;
let unsubscribeBridge: (() => void) | null = null;
const maximizedListeners = new Set<() => void>();

function publishMaximized(value: boolean) {
  maximized = value;
  maximizedListeners.forEach((listener) => listener());
}

export function subscribeWindowMaximized(listener: () => void): () => void {
  maximizedListeners.add(listener);
  const controls = getWindowControls();
  if (controls && !unsubscribeBridge) {
    unsubscribeBridge = controls.onMaximizedChange(publishMaximized);
    controls.isMaximized().then(publishMaximized).catch(() => {});
  }
  return () => {
    maximizedListeners.delete(listener);
    if (maximizedListeners.size === 0 && unsubscribeBridge) {
      unsubscribeBridge();
      unsubscribeBridge = null;
    }
  };
}

export function getWindowMaximized(): boolean {
  return maximized;
}
