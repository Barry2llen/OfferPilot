import { spawn as nodeSpawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { forwardUtf8, pythonEnvironment } from './runtime-output.mjs'
import { terminateProcessTree } from './process-cleanup.mjs'

export function createDevLauncher({
  cwd,
  executable,
  args = ['.', '--no-sandbox'],
  spawn = nodeSpawn,
  forceStop = terminateProcessTree,
  timeoutMs = 3000,
  host = process,
  stdout = process.stdout,
  stderr = process.stderr,
  onExit = code => {
    stdout.write('', () => stderr.write('', () => process.exit(code)))
  },
}) {
  let current
  let queue = Promise.resolve()
  let closing = false
  let hooked = false
  const report = message => stderr.write(`${message}\n`)

  function cleanOwnedProcesses(record) {
    for (const [pid, group] of [...record.ownedPids].reverse()) {
      if (forceStop(pid, { group, force: true })) record.ownedPids.delete(pid)
    }
  }

  function enqueue(action) {
    queue = queue.then(action).catch(error => {
      report(`[electron-dev] ${error.message}`)
      onExit(1)
    })
    return queue
  }

  function hookExit() {
    if (hooked) return
    hooked = true
    host.once('exit', () => {
      if (current) {
        if (current.child.pid) forceStop(current.child.pid, { group: process.platform !== 'win32', force: true })
        cleanOwnedProcesses(current)
      }
    })
    for (const signal of ['SIGINT', 'SIGTERM']) {
      host.once(signal, () => {
        void close().then(() => onExit(signal === 'SIGINT' ? 130 : 143))
      })
    }
  }

  function startProcess() {
    if (closing || current) return
    hookExit()
    const electron = executable ?? createRequire(import.meta.url)('electron')
    const child = spawn(electron, args, {
      cwd,
      env: { ...process.env, ...pythonEnvironment },
      stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
      // Electron is the user-facing GUI. SW_HIDE in its startup info can
      // suppress BrowserWindow.show() on Windows even after the page is ready.
      windowsHide: false,
      detached: process.platform !== 'win32',
    })
    const record = { child, exited: false, expectedStop: false, ownedPids: new Map() }
    current = record
    // The plugin's renderer reload hook checks this property. Its startup/exit
    // helpers are deliberately not used: they kill already-exited Windows PIDs.
    host.electronApp = child
    const outputs = [
      forwardUtf8(child.stdout, stdout, 'electron:stdout'),
      forwardUtf8(child.stderr, stderr, 'electron:stderr'),
    ]
    record.closed = new Promise(resolve => {
      child.once('error', error => {
        record.spawnError = true
        report(`[electron-dev] spawn failed error=${error.code ?? 'unknown'}: ${error.message}`)
      })
      child.on('message', message => {
        if (message?.type !== 'offerpilot:managed-pid' || !Number.isSafeInteger(message.pid)
          || message.pid <= 0 || message.pid === process.pid || message.pid === child.pid) return
        if (message.active) record.ownedPids.set(message.pid, message.group === true)
        else record.ownedPids.delete(message.pid)
      })
      child.once('exit', () => {
        record.exited = true
        cleanOwnedProcesses(record)
      })
      child.once('close', async code => {
        await Promise.all(outputs.map(output => output.readableEnded
          ? Promise.resolve() : new Promise(done => output.once('end', done))))
        if (current === record) {
          current = undefined
          host.electronApp = undefined
        }
        resolve()
        if (!record.expectedStop && !closing) onExit(record.spawnError ? 1 : code ?? 1)
      })
    })
  }

  async function stopCurrent() {
    const record = current
    if (!record) return
    record.expectedStop = true
    if (!record.exited && record.child.connected) {
      try {
        record.child.send('offerpilot:shutdown', () => {})
      } catch {
        // The child may disconnect between the check and send.
      }
    }
    let timer
    const graceful = await Promise.race([
      record.closed.then(() => true),
      new Promise(resolve => { timer = setTimeout(() => resolve(false), timeoutMs) }),
    ])
    clearTimeout(timer)
    if (!graceful) {
      if (!record.exited && record.child.pid && !forceStop(record.child.pid, {
        group: process.platform !== 'win32', force: true,
      })) {
        throw new Error(`Cannot stop Electron pid=${record.child.pid}`)
      }
      cleanOwnedProcesses(record)
      // Never start a replacement until the previous child's pipes have closed.
      let closeTimer
      try {
        await Promise.race([
          record.closed,
          new Promise((_, reject) => {
            closeTimer = setTimeout(() => reject(new Error(`Electron pipes did not close pid=${record.child.pid}`)), 2000)
          }),
        ])
      } finally {
        clearTimeout(closeTimer)
      }
    }
  }

  function close() {
    closing = true
    return enqueue(stopCurrent)
  }

  return {
    ensureStarted: () => enqueue(startProcess),
    restart: () => enqueue(async () => {
      await stopCurrent()
      startProcess()
    }),
    close,
  }
}
