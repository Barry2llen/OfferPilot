import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { EventEmitter } from 'node:events'
import { mkdtemp, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { Writable } from 'node:stream'
import { test } from 'node:test'
import { createDevLauncher } from '../scripts/dev-launcher.mjs'
import { isProcessAlive } from '../scripts/process-cleanup.mjs'

test('the development launcher actually shows the Windows Electron GUI', {
  skip: process.platform !== 'win32', timeout: 20_000,
}, async t => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'offerpilot-window-test-'))
  const entry = path.join(root, 'main.cjs')
  await writeFile(entry, `
    const { app, BrowserWindow } = require('electron');
    const path = require('node:path');
    app.setPath('userData', path.join(__dirname, 'user-data'));
    process.on('message', message => {
      if (message === 'offerpilot:shutdown') app.quit();
    });
    app.whenReady().then(() => {
      const window = new BrowserWindow({ show: false, width: 300, height: 180 });
      window.once('ready-to-show', () => {
        window.show();
        console.log('WINDOW_STATE=' + JSON.stringify({ visible: window.isVisible() }));
      });
      window.loadURL('data:text/html;charset=utf-8,<title>OfferPilot startup test</title><p>Window visibility test</p>');
    });
  `)
  let output = ''
  let errors = ''
  let child
  const exits = []
  const launcher = createDevLauncher({
    cwd: root,
    executable: createRequire(import.meta.url)('electron'),
    args: [entry],
    host: new EventEmitter(),
    spawn(...args) { child = spawn(...args); return child },
    stdout: new Writable({ write(chunk, _encoding, done) { output += chunk; done() } }),
    stderr: new Writable({ write(chunk, _encoding, done) { errors += chunk; done() } }),
    onExit: code => exits.push(code),
  })
  t.after(() => launcher.close())
  await launcher.ensureStarted()
  const deadline = Date.now() + 10_000
  while (!output.includes('WINDOW_STATE=')) {
    assert.equal(exits.length, 0, `Electron exited before showing its window: ${errors}`)
    assert.ok(Date.now() < deadline, `Window did not become ready: ${errors}`)
    await new Promise(resolve => setTimeout(resolve, 20))
  }
  const state = JSON.parse(output.match(/WINDOW_STATE=(.*)/)[1])
  assert.equal(state.visible, true, 'Windows must not suppress the first BrowserWindow.show()')
  await launcher.close()
  assert.equal(isProcessAlive(child.pid), false)
  assert.deepEqual(exits, [])
})
