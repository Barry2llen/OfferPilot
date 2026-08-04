import { app, BrowserWindow, dialog, Menu } from 'electron'
import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { createWriteStream, existsSync, mkdirSync, writeFileSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const appRoot = path.join(__dirname, '..')

process.env.APP_ROOT = process.env.APP_ROOT || appRoot
process.env.VITE_PUBLIC = path.join(process.env.APP_ROOT, 'public')

interface ManagedProcess {
  name: string
  child: ChildProcessWithoutNullStreams
  trackedPids: Set<number>
}

interface RuntimeServices {
  apiBaseUrl: string
  appUrl: string
}

let mainWindow: BrowserWindow | null = null
let managedProcesses: ManagedProcess[] = []

app.setName('OfferPilot')

const singleInstanceLock = app.requestSingleInstanceLock()
if (!singleInstanceLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  })

  app.whenReady().then(startApplication)
}

app.on('before-quit', stopManagedProcesses)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && process.env.OFFER_PILOT_APP_URL) {
    createWindow(process.env.OFFER_PILOT_APP_URL)
  }
})

async function startApplication() {
  try {
    configureApplicationMenu()

    const services = app.isPackaged
      ? await startProductionServices()
      : await startDevelopmentServices()

    process.env.OFFER_PILOT_API_BASE_URL = services.apiBaseUrl
    process.env.OFFER_PILOT_APP_URL = services.appUrl
    createWindow(services.appUrl)
  } catch (error) {
    stopManagedProcesses()
    showStartupFailure(error)
  }
}

async function startDevelopmentServices(): Promise<RuntimeServices> {
  const backendDir = resolveProjectDir(
    'OFFER_PILOT_BACKEND_DIR',
    'backend',
    'pyproject.toml',
  )
  const frontendDir = resolveProjectDir(
    'OFFER_PILOT_FRONTEND_DIR',
    'frontend',
    'package.json',
  )
  const backendPort = await findAvailablePort(8080)
  const frontendPort = await findAvailablePort(3000)
  const apiBaseUrl = `http://127.0.0.1:${backendPort}`
  const appUrl = `http://127.0.0.1:${frontendPort}`
  const backendProcess = startManagedProcess('backend-dev', 'uv', [
    'run',
    'uvicorn',
    'main:app',
    '--host',
    '127.0.0.1',
    '--port',
    String(backendPort),
  ], backendDir, {
    PYTHONUNBUFFERED: '1',
  })

  trackBackendServerPid(backendProcess)

  startManagedProcess('frontend-dev', resolveNpmCommand(), [
    'run',
    'dev',
    '--',
    '--port',
    String(frontendPort),
  ], frontendDir, {
    VITE_API_URL: apiBaseUrl,
  })

  await waitForUrl(`${apiBaseUrl}/health`, 'backend')
  await waitForUrl(appUrl, 'frontend')

  return { apiBaseUrl, appUrl }
}

async function startProductionServices(): Promise<RuntimeServices> {
  const backendPort = await findAvailablePort(8080)
  const apiBaseUrl = `http://127.0.0.1:${backendPort}`
  const appUrl = apiBaseUrl
  const runtimeDir = ensureBackendRuntimeConfig()
  const backendExe = resolvePackagedBackendExecutable()
  const frontendDist = resolvePackagedFrontendDist()

  startManagedProcess('backend', backendExe, [
    '--host',
    '127.0.0.1',
    '--port',
    String(backendPort),
    '--runtime-dir',
    runtimeDir,
    '--frontend-dist',
    frontendDist,
  ], runtimeDir, {
    PYTHONUNBUFFERED: '1',
  })

  await waitForUrl(`${apiBaseUrl}/health`, 'backend')
  await waitForUrl(appUrl, 'frontend')

  return { apiBaseUrl, appUrl }
}

function createWindow(targetUrl: string) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 1040,
    minHeight: 680,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#f7f7f4',
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#ffffff',
      symbolColor: '#18181b',
      height: 48,
    },
    icon: path.join(process.env.VITE_PUBLIC || path.join(appRoot, 'public'), 'electron-vite.svg'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show()
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  mainWindow.loadURL(targetUrl).catch((error: unknown) => {
    showStartupFailure(error)
  })
}

function configureApplicationMenu() {
  if (process.platform !== 'darwin') {
    Menu.setApplicationMenu(null)
  }
}

function showStartupFailure(error: unknown) {
  const message = error instanceof Error ? error.message : String(error)
  dialog.showErrorBox('OfferPilot 启动失败', message)

  if (mainWindow) return

  mainWindow = new BrowserWindow({
    width: 760,
    height: 420,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  const html = `
    <html lang="zh-CN">
      <body style="font-family: system-ui, sans-serif; padding: 32px; color: #1f2933;">
        <h1 style="font-size: 22px;">OfferPilot 启动失败</h1>
        <p style="line-height: 1.6;">${escapeHtml(message)}</p>
      </body>
    </html>
  `
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`).catch(() => undefined)
}

function startManagedProcess(
  name: string,
  command: string,
  args: string[],
  cwd: string,
  env: NodeJS.ProcessEnv,
) {
  if (!existsSync(cwd)) {
    throw new Error(`${name} working directory does not exist: ${cwd}`)
  }

  let child: ChildProcessWithoutNullStreams
  try {
    child = spawn(command, args, {
      cwd,
      env: { ...process.env, ...env },
      stdio: 'pipe',
      windowsHide: true,
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    throw new Error(`Failed to start ${name} with "${formatCommand(command, args)}" in ${cwd}: ${message}`)
  }
  const managed = { name, child, trackedPids: new Set<number>() }
  if (child.pid) {
    managed.trackedPids.add(child.pid)
  }
  managedProcesses.push(managed)
  attachProcessLogging(managed)

  child.on('error', (error) => {
    console.error(`[${name}] ${error.message}`)
  })

  child.on('exit', (code, signal) => {
    console.info(`[${name}] exited with code=${code ?? 'null'} signal=${signal ?? 'null'}`)
  })

  return managed
}

function attachProcessLogging(processInfo: ManagedProcess) {
  const logsDir = path.join(app.getPath('userData'), 'logs')
  mkdirSync(logsDir, { recursive: true })
  const logStream = createWriteStream(path.join(logsDir, `${processInfo.name}.log`), {
    flags: 'a',
  })
  const prefix = `[${new Date().toISOString()}]`

  logStream.write(`${prefix} Starting ${processInfo.name}\n`)
  processInfo.child.stdout.on('data', (chunk: Buffer) => {
    logStream.write(chunk)
  })
  processInfo.child.stderr.on('data', (chunk: Buffer) => {
    logStream.write(chunk)
  })
  processInfo.child.on('close', (code, signal) => {
    logStream.write(`\n[${new Date().toISOString()}] exited code=${code ?? 'null'} signal=${signal ?? 'null'}\n`)
    logStream.end()
  })
}

function stopManagedProcesses() {
  for (const processInfo of [...managedProcesses].reverse()) {
    stopManagedProcess(processInfo)
  }
  managedProcesses = []
}

function stopManagedProcess(processInfo: ManagedProcess) {
  const pids = [...processInfo.trackedPids]
  if (processInfo.child.pid) {
    pids.push(processInfo.child.pid)
  }

  for (const pid of [...new Set(pids)].reverse()) {
    killProcessTree(pid)
  }

  if (!processInfo.child.killed) {
    try {
      processInfo.child.kill()
    } catch {
      // The direct child may already be gone after process-tree cleanup.
    }
  }
}

function killProcessTree(pid: number) {
  if (process.platform === 'win32') {
    killWindowsProcessTree(pid)
    return
  }

  try {
    process.kill(pid, 'SIGTERM')
  } catch {
    // The process may have exited between tracking and cleanup.
  }
}

function killWindowsProcessTree(pid: number) {
  spawnSync('taskkill.exe', ['/pid', String(pid), '/t', '/f'], {
    stdio: 'ignore',
    windowsHide: true,
  })
}

function trackBackendServerPid(processInfo: ManagedProcess) {
  processInfo.child.stdout.on('data', (chunk: Buffer) => {
    const output = chunk.toString('utf-8')
    const match = output.match(/Started server process \[(\d+)]/)
    if (match) {
      processInfo.trackedPids.add(Number(match[1]))
    }
  })
}

function resolveProjectDir(envName: string, folderName: string, markerFile: string): string {
  const envValue = process.env[envName]
  const candidates = [
    envValue ? path.resolve(envValue) : '',
    path.resolve(process.cwd(), '..', folderName),
    path.resolve(process.env.APP_ROOT || appRoot, '..', folderName),
    path.resolve(__dirname, '..', '..', folderName),
  ].filter(Boolean)

  for (const candidate of candidates) {
    if (existsSync(path.join(candidate, markerFile))) {
      return candidate
    }
  }

  throw new Error(`Cannot locate ${folderName}. Set ${envName} to the project path.`)
}

function resolvePackagedBackendExecutable(): string {
  const exeName = process.platform === 'win32' ? 'offer-pilot-api.exe' : 'offer-pilot-api'
  const executable = path.join(process.resourcesPath, 'backend', 'offer-pilot-api', exeName)
  if (!existsSync(executable)) {
    throw new Error(`Packaged backend executable not found: ${executable}`)
  }
  return executable
}

function resolvePackagedFrontendDist(): string {
  const frontendDist = path.join(process.resourcesPath, 'frontend')
  if (!existsSync(path.join(frontendDist, 'index.html'))) {
    throw new Error(`Packaged frontend build not found: ${frontendDist}`)
  }
  return frontendDist
}

function ensureBackendRuntimeConfig(): string {
  const runtimeDir = path.join(app.getPath('home'), '.offerpilot')
  const dataDir = path.join(runtimeDir, 'data')
  const resumeDir = path.join(dataDir, 'resumes')
  const configPath = path.join(runtimeDir, 'config.yaml')

  mkdirSync(resumeDir, { recursive: true })
  mkdirSync(path.join(runtimeDir, 'logs'), { recursive: true })

  if (!existsSync(configPath)) {
    const databasePath = toYamlPath(path.join(dataDir, 'offer_pilot.db'))
    const resumeUploadDir = toYamlPath(resumeDir)
    writeFileSync(configPath, [
      'database:',
      '  type: "sqlite"',
      `  path: "${databasePath}"`,
      '  echo: false',
      '',
      `resume_upload_dir: "${resumeUploadDir}"`,
      '',
      'cors:',
      '  allow_origins:',
      '    - "*"',
      '  allow_credentials: false',
      '  allow_methods:',
      '    - "*"',
      '  allow_headers:',
      '    - "*"',
      '',
      'debug: false',
      'exa_api_key: null',
      '',
    ].join('\n'), 'utf-8')
  }

  return runtimeDir
}

function findAvailablePort(preferredPort: number): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.on('error', () => {
      if (preferredPort === 0) {
        reject(new Error('Unable to find an available port'))
        return
      }
      resolve(findAvailablePort(0))
    })
    server.listen(preferredPort, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : preferredPort
      server.close(() => resolve(port))
    })
  })
}

async function waitForUrl(url: string, label: string, timeoutMs = 60_000) {
  const startedAt = Date.now()
  let lastError = ''

  while (Date.now() - startedAt < timeoutMs) {
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 2_000)
      const response = await fetch(url, { signal: controller.signal }).finally(() => {
        clearTimeout(timeout)
      })
      if (response.status < 500) {
        return
      }
      lastError = `HTTP ${response.status}`
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error)
    }

    await delay(500)
  }

  throw new Error(`${label} did not become ready at ${url}${lastError ? `: ${lastError}` : ''}`)
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function resolveNpmCommand() {
  return process.platform === 'win32' ? 'npm.cmd' : 'npm'
}

function formatCommand(command: string, args: string[]) {
  return [command, ...args].join(' ')
}

function toYamlPath(targetPath: string) {
  return targetPath.replace(/\\/g, '/')
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}
