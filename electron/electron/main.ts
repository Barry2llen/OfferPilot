import { app, BrowserWindow, dialog, Menu } from 'electron'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { createWriteStream, existsSync, mkdirSync, writeFileSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { backendEnvironment } from './backend-environment'
import { forwardUtf8, prepareUtf8Log, pythonEnvironment, Utf8Decoder } from '../scripts/runtime-output.mjs'
import { terminateProcessTree } from '../scripts/process-cleanup.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const appRoot = path.join(__dirname, '..')

process.env.APP_ROOT = process.env.APP_ROOT || appRoot
process.env.VITE_PUBLIC = path.join(process.env.APP_ROOT, 'public')

interface ManagedProcess {
  name: string
  child: ChildProcessWithoutNullStreams
  trackedPids: Set<number>
  stopping: boolean
  closed: Promise<void>
}

interface RuntimeServices {
  apiBaseUrl: string
  appUrl: string
}

let mainWindow: BrowserWindow | null = null
let managedProcesses: ManagedProcess[] = []
let shuttingDown = false
let shutdownComplete = false
let shutdown: Promise<void> | undefined

app.setName('OfferPilot')

const runtimeOverride = process.env.OFFER_PILOT_RUNTIME_DIR
if (runtimeOverride) {
  const userData = path.join(path.resolve(runtimeOverride), 'electron')
  mkdirSync(userData, { recursive: true })
  app.setPath('userData', userData)
}

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

app.on('before-quit', (event) => {
  if (shutdownComplete) return
  event.preventDefault()
  shuttingDown = true
  shutdown ??= stopManagedProcesses().finally(() => {
    shutdownComplete = true
    app.quit()
  })
})

if (!app.isPackaged && process.send) {
  process.on('message', (message) => {
    if (message === 'offerpilot:shutdown') app.quit()
  })
  process.once('disconnect', () => app.quit())
}

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

    if (shuttingDown) return
    process.env.OFFER_PILOT_API_BASE_URL = services.apiBaseUrl
    process.env.OFFER_PILOT_APP_URL = services.appUrl
    createWindow(services.appUrl)
  } catch (error) {
    await stopManagedProcesses()
    if (!shuttingDown) showStartupFailure(error)
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
  const frontendCommand = resolveFrontendDevCommand(frontendPort)
  const backendProcess = startManagedProcess('backend-dev', 'uv', [
    'run',
    'python',
    'run_server.py',
    '--host',
    '127.0.0.1',
    '--port',
    String(backendPort),
  ], backendDir, {
    ...pythonEnvironment,
  })

  trackBackendServerPid(backendProcess)

  startManagedProcess('frontend-dev', frontendCommand.command, frontendCommand.args, frontendDir, {
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
    ...backendEnvironment(backendExe),
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
      env: { ...process.env, ...env, ...pythonEnvironment },
      stdio: 'pipe',
      windowsHide: true,
      detached: process.platform !== 'win32',
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    throw new Error(`Failed to start ${name} with "${formatCommand(command, args)}" in ${cwd}: ${message}`)
  }
  const managed: ManagedProcess = {
    name, child, trackedPids: new Set<number>(), stopping: false, closed: Promise.resolve(),
  }
  if (child.pid) {
    managed.trackedPids.add(child.pid)
    notifyManagedPid(child.pid, true, process.platform !== 'win32')
  }
  managedProcesses.push(managed)
  attachProcessLogging(managed)

  child.on('error', (error) => {
    console.error(`[${name}] ${error.message}`)
  })

  child.on('exit', (code, signal) => {
    console.info(`[${name}] ${managed.stopping ? 'stopped during shutdown' : 'exited'} code=${code ?? 'null'} signal=${signal ?? 'null'}`)
  })

  return managed
}

function attachProcessLogging(processInfo: ManagedProcess) {
  const logsDir = path.join(app.getPath('userData'), 'logs')
  mkdirSync(logsDir, { recursive: true })
  const filename = path.join(logsDir, `${processInfo.name}.log`)
  const archive = prepareUtf8Log(filename)
  const logStream = createWriteStream(filename, {
    flags: 'a',
    encoding: 'utf8',
  })
  const prefix = `[${new Date().toISOString()}]`

  if (archive) logStream.write(`${prefix} Previous non-UTF-8 log archived as ${archive}\n`)
  logStream.write(`${prefix} Starting ${processInfo.name}\n`)
  const outputs = [
    forwardUtf8(processInfo.child.stdout, logStream, `${processInfo.name}:stdout`),
    forwardUtf8(processInfo.child.stderr, logStream, `${processInfo.name}:stderr`),
  ]
  processInfo.closed = new Promise((resolve) => {
    let childClosed = false
    let logFailed = false
    logStream.on('error', (error: NodeJS.ErrnoException) => {
      logFailed = true
      console.error(`[${processInfo.name}] log write failed error=${error.code ?? 'unknown'}`)
      if (childClosed) resolve()
    })
    processInfo.child.once('close', async (code, signal) => {
      childClosed = true
      for (const pid of processInfo.trackedPids) notifyManagedPid(pid, false)
      await Promise.all(outputs.map(output => output.readableEnded
        ? Promise.resolve() : new Promise<void>(done => output.once('end', done))))
      if (logFailed) {
        resolve()
        return
      }
      logStream.end(`\n[${new Date().toISOString()}] exited code=${code ?? 'null'} signal=${signal ?? 'null'}\n`, resolve)
    })
  })
}

async function stopManagedProcesses() {
  const processes = managedProcesses
  managedProcesses = []
  for (const processInfo of [...processes].reverse()) {
    processInfo.stopping = true
    stopManagedProcess(processInfo)
  }
  let timer: ReturnType<typeof setTimeout> | undefined
  const graceful = await Promise.race([
    Promise.all(processes.map(processInfo => processInfo.closed)).then(() => true),
    new Promise<boolean>(resolve => { timer = setTimeout(() => resolve(false), 2000) }),
  ])
  clearTimeout(timer)
  if (!graceful) {
    for (const processInfo of [...processes].reverse()) {
      stopManagedProcess(processInfo, true)
    }
  }
}

function stopManagedProcess(processInfo: ManagedProcess, force = false) {
  const pids = [...processInfo.trackedPids]
  if (processInfo.child.pid) {
    pids.push(processInfo.child.pid)
  }

  for (const pid of [...new Set(pids)].reverse()) {
    terminateProcessTree(pid, {
      group: pid === processInfo.child.pid && process.platform !== 'win32',
      force,
    })
  }
}

function notifyManagedPid(pid: number, active: boolean, group = false) {
  if (!app.isPackaged && process.connected && process.send) {
    try {
      process.send({ type: 'offerpilot:managed-pid', pid, active, group }, () => {})
    } catch {
      // Shutdown may close the private channel before managed processes exit.
    }
  }
}

function trackBackendServerPid(processInfo: ManagedProcess) {
  const decoder = new Utf8Decoder('backend:pid')
  let tail = ''
  processInfo.child.stdout.on('data', (chunk: Buffer) => {
    tail = (tail + decoder.write(chunk)).slice(-4096)
    const match = tail.match(/Started server process \[(\d+)]/)
    if (match) {
      const pid = Number(match[1])
      if (!processInfo.trackedPids.has(pid)) {
        processInfo.trackedPids.add(pid)
        notifyManagedPid(pid, true)
      }
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
  const runtimeDir = runtimeOverride
    ? path.resolve(runtimeOverride)
    : path.join(app.getPath('home'), '.offerpilot')
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
    if (shuttingDown) throw new Error('Application is shutting down')
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

function resolveFrontendDevCommand(port: number) {
  const pnpmArgs = ['run', 'dev', '--port', String(port)]

  if (process.platform === 'win32') {
    return {
      command: process.env.ComSpec || 'cmd.exe',
      args: ['/d', '/s', '/c', 'pnpm.cmd', ...pnpmArgs],
    }
  }

  return {
    command: 'pnpm',
    args: pnpmArgs,
  }
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
