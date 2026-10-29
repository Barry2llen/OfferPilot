import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { parseArgs } from 'node:util'
import { _electron as electron } from 'playwright-core'
import { backendEnvironment } from '../electron/backend-environment.ts'
import { assertSelfContainedSymlinks } from './linux-libraries.mjs'

const { values } = parseArgs({ options: {
  executable: { type: 'string' },
  resources: { type: 'string' },
  output: { type: 'string' },
} })
if (process.platform !== 'linux' || !values.executable || !values.resources) {
  throw new Error('Usage: pnpm test:linux --executable /path/to/app --resources /path/to/resources [--output /tmp/evidence]')
}

const output = values.output ? path.resolve(values.output) : await mkdtemp(path.join(os.tmpdir(), 'offerpilot-smoke-'))
await mkdir(output, { recursive: true })
const runtime = await mkdtemp(path.join(os.tmpdir(), 'offerpilot-runtime-'))
const executable = path.resolve(values.executable)
const resources = path.resolve(values.resources)
const backend = path.join(resources, 'backend/offer-pilot-api/offer-pilot-api')
const errors = []
const stderr = []
let application
let backendPids = []
let apiBaseUrl

async function runningBackendPids() {
  const pids = []
  for (const entry of await readdir('/proc')) {
    if (!/^\d+$/.test(entry)) continue
    const command = await readFile(`/proc/${entry}/cmdline`, 'utf8').catch(() => '')
    const args = command.split('\0')
    if (args.includes('--runtime-dir') && args.includes(runtime)) pids.push(Number(entry))
  }
  return pids
}

async function waitForShutdown() {
  const deadline = Date.now() + 15_000
  while (Date.now() < deadline) {
    if ((await runningBackendPids()).length === 0) return
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  throw new Error(`Backend processes survived closing the app: ${backendPids.join(', ')}`)
}

try {
  assert.ok(existsSync(path.join(resources, 'frontend/index.html')), 'Packaged frontend is missing')
  await assertSelfContainedSymlinks(path.dirname(backend))
  const selfCheck = spawnSync(backend, ['--self-check'], {
    cwd: runtime,
    env: { ...process.env, ...backendEnvironment(backend) },
    encoding: 'utf8',
    timeout: 120_000,
  })
  await writeFile(path.join(output, 'self-check.log'), `${selfCheck.stdout ?? ''}${selfCheck.stderr ?? ''}`)
  assert.equal(selfCheck.status, 0, `Frozen backend self-check failed: ${selfCheck.error ?? selfCheck.stderr}`)
  assert.equal(JSON.parse(selfCheck.stdout.trim().split('\n').at(-1)).ok, true)

  const environment = { ...process.env, OFFER_PILOT_RUNTIME_DIR: runtime, APPIMAGE_EXTRACT_AND_RUN: '1' }
  delete environment.ELECTRON_RUN_AS_NODE
  application = await electron.launch({
    executablePath: executable,
    cwd: runtime,
    env: environment,
    timeout: 120_000,
    // CI runners may restrict user namespaces. Production desktop-entry policy is unchanged.
    chromiumSandbox: false,
  })
  application.process().stderr?.on('data', data => stderr.push(data.toString()))
  await application.evaluate(({ dialog }) => {
    dialog.showErrorBox = (title, content) => console.error(`${title}: ${content}`)
  })
  const window = await application.firstWindow({ timeout: 90_000 })
  window.on('pageerror', error => errors.push(error.message))
  window.on('console', message => {
    if (message.type() === 'error' && !/Electron Security Warning/.test(message.text())) errors.push(message.text())
  })
  await window.waitForURL(/^http:\/\/127\.0\.0\.1:\d+\//, { timeout: 90_000 })
  await window.locator('nav').waitFor()
  await window.locator('main textarea').first().waitFor({ state: 'visible', timeout: 30_000 })
  assert.match(await window.title(), /OfferPilot/)
  assert.ok((await window.locator('body').innerText()).length > 30, 'Blank app shell')
  assert.equal(await window.locator('vite-error-overlay').count(), 0)
  apiBaseUrl = new URL(window.url()).origin
  const health = await fetch(`${apiBaseUrl}/health`)
  assert.equal(health.status, 200)
  assert.deepEqual(await health.json(), { message: 'Hello World!' })
  assert.equal(await window.evaluate(() => window.offerPilotRuntime.apiBaseUrl), apiBaseUrl)
  await window.screenshot({ path: path.join(output, 'home.png') })

  await window.locator('a[href="/resumes"]').first().click()
  await window.waitForURL(`${apiBaseUrl}/resumes`)
  await window.locator('main h1').waitFor({ state: 'visible' })
  await window.reload()
  await window.locator('main h1').waitFor({ state: 'visible' })
  assert.equal(new URL(window.url()).pathname, '/resumes')
  assert.equal((await fetch(`${apiBaseUrl}/assets/missing-smoke-test.js`)).status, 404)
  await window.screenshot({ path: path.join(output, 'resumes.png') })

  const webPreferences = await application.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences())
  assert.equal(webPreferences.contextIsolation, true)
  assert.equal(webPreferences.nodeIntegration, false)
  backendPids = await runningBackendPids()
  assert.ok(backendPids.length > 0, 'Managed backend process was not found')
  assert.deepEqual(errors, [], 'Renderer errors')
  await application.close()
  application = undefined
  await waitForShutdown()
  const reachable = await fetch(`${apiBaseUrl}/health`, { signal: AbortSignal.timeout(1_000) }).then(() => true, () => false)
  assert.equal(reachable, false, 'Backend HTTP server survived closing the app')
  await writeFile(path.join(output, 'result.json'), `${JSON.stringify({ ok: true, executable, apiBaseUrl, runtime, backendPids, errors }, null, 2)}\n`)
  console.log(`Linux packaged-app smoke check passed. Evidence: ${output}`)
} finally {
  if (application) await application.close().catch(error => stderr.push(String(error)))
  await writeFile(path.join(output, 'electron-stderr.log'), stderr.join(''))
  if (existsSync(runtime)) {
    const { cp } = await import('node:fs/promises')
    await cp(runtime, path.join(output, 'runtime'), { recursive: true })
  }
}
