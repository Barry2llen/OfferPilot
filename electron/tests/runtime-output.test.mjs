import assert from 'node:assert/strict'
import { mkdtemp, readFile, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { PassThrough, Writable } from 'node:stream'
import { once } from 'node:events'
import { test } from 'node:test'
import { Utf8Decoder, forwardUtf8, prepareUtf8Log, pythonEnvironment } from '../scripts/runtime-output.mjs'
import { terminateProcessTree } from '../scripts/process-cleanup.mjs'

test('UTF-8 text survives every possible chunk boundary including Chinese and emoji', () => {
  const text = '参数错误。中文路径 D:/简历/测试 😀\nnext line\r\n'
  const bytes = Buffer.from(text)
  for (let offset = 0; offset <= bytes.length; offset++) {
    const decoder = new Utf8Decoder()
    assert.equal(decoder.write(bytes.subarray(0, offset)) + decoder.write(bytes.subarray(offset)) + decoder.end(), text)
  }
  const decoder = new Utf8Decoder()
  assert.equal([...bytes].map(byte => decoder.write(Buffer.from([byte]))).join('') + decoder.end(), text)
})

test('invalid and incomplete bytes are escaped without silently replacing or guessing text', () => {
  for (const bytes of [Buffer.from([0xff]), Buffer.from([0xed, 0xa0, 0x80]), Buffer.from([0xf0, 0x9f]), Buffer.from([0xc0, 0xaf])]) {
    const decoder = new Utf8Decoder('native')
    const text = decoder.write(bytes) + decoder.end()
    assert.match(text, /encoding-error: native/)
    assert.match(text, /\\x[0-9a-f]{2}/)
    assert.ok(!text.includes('\ufffd'))
  }
  const decoder = new Utf8Decoder()
  const text = decoder.write(Buffer.concat([Buffer.from('正常'), Buffer.from([0xff]), Buffer.from('结束😀')])) + decoder.end()
  assert.ok(text.includes('正常\\xff结束😀'))
})

test('forwarding flushes incomplete bytes on EOF and leaves the destination open', async () => {
  const input = new PassThrough()
  let text = ''
  const output = new Writable({ write(chunk, _encoding, done) { text += chunk.toString('utf8'); done() } })
  const forwarding = forwardUtf8(input, output, 'test')
  const finished = once(forwarding, 'end')
  input.write(Buffer.from('中文😀'))
  input.end(Buffer.from([0xe4]))
  await finished
  assert.match(text, /中文😀/)
  assert.match(text, /\\xe4/)
  assert.equal(output.writableEnded, false)
})

test('legacy log bytes are archived exactly; valid UTF-8 logs are kept', async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'offerpilot-output-'))
  const file = path.join(directory, '中文.log')
  const legacy = Buffer.from([0xb4, 0xed, 0xce, 0xf3])
  await writeFile(file, legacy)
  const archive = prepareUtf8Log(file)
  assert.deepEqual(await readFile(archive), legacy)
  await writeFile(file, '新日志😀', 'utf8')
  assert.equal(prepareUtf8Log(file), undefined)
  assert.equal(await readFile(file, 'utf8'), '新日志😀')
  assert.equal(prepareUtf8Log(path.join(directory, 'absent.log')), undefined)
})

test('Python children get an explicit UTF-8 encoding contract', () => {
  assert.deepEqual(pythonEnvironment, {
    PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8:backslashreplace', PYTHONUNBUFFERED: '1',
  })
})

function noProcess() { throw Object.assign(new Error('missing'), { code: 'ESRCH' }) }

test('cleanup of an already-exited process never invokes taskkill', () => {
  assert.equal(terminateProcessTree(123, { kill: noProcess, run() { assert.fail('taskkill must not run') } }), true)
})

test('a Windows cleanup race is benign and never forwards localized stderr', () => {
  let checks = 0
  const messages = []
  const kill = () => { if (checks++ > 0) noProcess() }
  assert.equal(terminateProcessTree(123, {
    platform: 'win32', kill, report: text => messages.push(text),
    run(_command, _args, options) {
      assert.equal(options.stdio, 'ignore')
      return { status: 128, stderr: Buffer.from([0xff]) }
    },
  }), true)
  assert.deepEqual(messages, [])
})

test('real cleanup failures report the operation, PID and code without native bytes', () => {
  const messages = []
  assert.equal(terminateProcessTree(123, {
    platform: 'win32', kill() {}, report: text => messages.push(text),
    run() { return { status: 5, stderr: Buffer.from([0xff]) } },
  }), false)
  assert.deepEqual(messages, ['[process-cleanup] taskkill failed pid=123 exit=5 error=none'])
})

test('POSIX managed process groups are terminated even if their leader has exited', () => {
  const signals = []
  assert.equal(terminateProcessTree(123, {
    platform: 'linux', group: true,
    kill(pid, signal) {
      signals.push([pid, signal])
      if (pid === 123) noProcess()
    },
  }), true)
  assert.ok(signals.some(([pid, signal]) => pid === -123 && signal === 'SIGTERM'))
})
