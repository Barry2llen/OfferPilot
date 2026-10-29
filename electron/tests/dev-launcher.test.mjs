import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { EventEmitter } from 'node:events'
import { mkdtemp, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { Writable } from 'node:stream'
import { test } from 'node:test'
import { createDevLauncher } from '../scripts/dev-launcher.mjs'
import { isProcessAlive } from '../scripts/process-cleanup.mjs'

async function until(check) {
  const deadline = Date.now() + 5000
  while (!check()) {
    assert.ok(Date.now() < deadline, 'Timed out waiting for child lifecycle')
    await new Promise(resolve => setTimeout(resolve, 10))
  }
}

async function fixture(t, { ignoreShutdown = false, timeoutMs = 1000, missing = false, ownedChild = false } = {}) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'offerpilot-launcher-'))
  const entry = path.join(directory, 'child.cjs')
  await writeFile(entry, `
    if (${ownedChild}) {
      const owned = require('node:child_process').spawn(process.execPath, ['-e', 'setInterval(()=>{},1000)'], {stdio:'ignore',windowsHide:true});
      process.send({type:'offerpilot:managed-pid',pid:owned.pid,active:true});
      process.stdout.write('owned=' + owned.pid + '\\n');
    }
    process.on('message', message => {
      if (message === 'offerpilot:shutdown' && !${ignoreShutdown}) process.exit(0);
      if (message === 'unexpected') process.exit(7);
    });
    const bytes = Buffer.from('中文😀 ready\\n');
    process.stdout.write(bytes.subarray(0, 2));
    setTimeout(() => process.stdout.write(bytes.subarray(2)), 5);
    process.stderr.write('AMD VideoProcessorGetOutputExtension failed: 参数错误。(0x80070057)\\n');
  `)
  const host = new EventEmitter()
  const children = []
  const exits = []
  const forced = []
  let stdout = ''
  let stderr = ''
  const launcher = createDevLauncher({
    cwd: directory, executable: process.execPath, timeoutMs, host,
    spawn(executable, _args, options) {
      assert.equal(options.env.PYTHONIOENCODING, 'utf-8:backslashreplace')
      assert.equal(options.windowsHide, false, 'the Electron GUI must not inherit SW_HIDE')
      const child = spawn(missing ? path.join(directory, 'missing.exe') : executable, [entry], options)
      children.push(child)
      return child
    },
    stdout: new Writable({ write(chunk, _encoding, done) { stdout += chunk; done() } }),
    stderr: new Writable({ write(chunk, _encoding, done) { stderr += chunk; done() } }),
    forceStop(pid) {
      forced.push(pid)
      try { process.kill(pid, 'SIGKILL') } catch (error) { if (error.code !== 'ESRCH') throw error }
      return true
    },
    onExit: code => exits.push(code),
  })
  t.after(async () => {
    await launcher.close()
    for (const child of children) {
      if (child.exitCode === null && child.signalCode === null && child.pid) child.kill('SIGKILL')
    }
  })
  return { launcher, host, children, exits, forced, output: () => ({ stdout, stderr }) }
}

test('preload updates reuse the child; main rebuilds serialize a graceful restart', async t => {
  const f = await fixture(t)
  await f.launcher.ensureStarted()
  await until(() => f.output().stdout.includes('ready'))
  await f.launcher.ensureStarted()
  assert.equal(f.children.length, 1)
  assert.equal(f.output().stdout, '中文😀 ready\n')
  assert.match(f.output().stderr, /failed: 参数错误/)
  await Promise.all([f.launcher.restart(), f.launcher.ensureStarted()])
  assert.equal(f.children.length, 2)
  assert.equal(f.children[0].exitCode, 0)
  await until(() => f.output().stdout.split('ready').length === 3)
  await Promise.all([f.launcher.close(), f.launcher.close()])
  f.host.emit('exit')
  assert.deepEqual(f.exits, [])
  assert.deepEqual(f.forced, [])
  assert.equal(f.children[1].exitCode, 0)
})

test('normal window close or unexpected exit is reported once without killing a dead PID', async t => {
  const f = await fixture(t)
  await f.launcher.ensureStarted()
  await until(() => f.output().stdout.includes('ready'))
  f.children[0].send('unexpected')
  await until(() => f.exits.length > 0)
  assert.deepEqual(f.exits, [7])
  f.host.emit('exit')
  assert.deepEqual(f.forced, [])
})

for (const signal of ['SIGINT', 'SIGTERM']) {
  test(`${signal} gracefully shuts down before exiting the parent`, async t => {
    const f = await fixture(t)
    await f.launcher.ensureStarted()
    await until(() => f.output().stdout.includes('ready'))
    f.host.emit(signal)
    await until(() => f.exits.length > 0)
    assert.deepEqual(f.exits, [signal === 'SIGINT' ? 130 : 143])
    assert.equal(f.children[0].exitCode, 0)
    assert.deepEqual(f.forced, [])
  })
}

test('unresponsive children are forced down only after the grace period', async t => {
  const f = await fixture(t, { ignoreShutdown: true, timeoutMs: 80 })
  await f.launcher.ensureStarted()
  await until(() => f.output().stdout.includes('ready'))
  const start = Date.now()
  await f.launcher.close()
  assert.ok(Date.now() - start >= 70)
  assert.deepEqual(f.forced, [f.children[0].pid])
  assert.deepEqual(f.exits, [])
})

test('spawn errors finish cleanly and are forwarded as readable diagnostics', async t => {
  const f = await fixture(t, { missing: true })
  await f.launcher.ensureStarted()
  await until(() => f.exits.length > 0)
  assert.deepEqual(f.exits, [1])
  assert.match(f.output().stderr, /spawn failed error=ENOENT/)
  assert.deepEqual(f.forced, [])
})

test('an Electron crash also cleans up the managed PIDs reported over private IPC', async t => {
  const f = await fixture(t, { ownedChild: true })
  await f.launcher.ensureStarted()
  await until(() => f.output().stdout.includes('ready'))
  const pid = Number(f.output().stdout.match(/owned=(\d+)/)[1])
  assert.equal(isProcessAlive(pid), true)
  f.children[0].send('unexpected')
  await until(() => f.exits.length > 0)
  await until(() => !isProcessAlive(pid))
  assert.deepEqual(f.forced, [pid])
})
