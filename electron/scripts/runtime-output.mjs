import { closeSync, mkdirSync, openSync, readSync, renameSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import path from 'node:path'
import { Transform } from 'node:stream'

export const pythonEnvironment = Object.freeze({
  PYTHONUTF8: '1',
  PYTHONIOENCODING: 'utf-8:backslashreplace',
  PYTHONUNBUFFERED: '1',
})

// Keep incomplete characters between chunks; escape invalid bytes without
// replacing valid text or guessing a different source encoding.
export class Utf8Decoder {
  pending = Buffer.alloc(0)

  constructor(label = 'output') {
    this.label = label
  }

  write(chunk, final = false) {
    const bytes = Buffer.concat([this.pending, Buffer.from(chunk)])
    this.pending = Buffer.alloc(0)
    let start = 0
    let offset = 0
    let output = ''
    let invalid = false
    while (offset < bytes.length) {
      const first = bytes[offset]
      const length = first < 0x80 ? 1 : first >= 0xc2 && first <= 0xdf ? 2
        : first >= 0xe0 && first <= 0xef ? 3 : first >= 0xf0 && first <= 0xf4 ? 4 : 0
      const available = Math.min(length, bytes.length - offset)
      let valid = length > 0
      for (let i = 1; i < available; i++) {
        const byte = bytes[offset + i]
        if (byte < 0x80 || byte > 0xbf || (i === 1 && (
          (first === 0xe0 && byte < 0xa0) || (first === 0xed && byte > 0x9f)
          || (first === 0xf0 && byte < 0x90) || (first === 0xf4 && byte > 0x8f)
        ))) valid = false
      }
      if (valid && available < length && !final) {
        this.pending = bytes.subarray(offset)
        break
      }
      if (valid && available === length) {
        offset += length
        continue
      }
      output += bytes.subarray(start, offset).toString('utf8')
      output += `\\x${first.toString(16).padStart(2, '0')}`
      invalid = true
      start = ++offset
    }
    output += bytes.subarray(start, offset).toString('utf8')
    return invalid ? `[encoding-error: ${this.label}] ${output}` : output
  }

  end() {
    return this.write(Buffer.alloc(0), true)
  }
}

export function forwardUtf8(source, destination, label = 'output', onText = () => {}) {
  const decoder = new Utf8Decoder(label)
  const forward = text => {
    if (text) onText(text)
    return text
  }
  const transform = new Transform({
    transform(chunk, _encoding, callback) {
      callback(null, forward(decoder.write(chunk)))
    },
    flush(callback) {
      callback(null, forward(decoder.end()))
    },
  })
  source.pipe(transform).pipe(destination, { end: false })
  return transform
}

export function prepareUtf8Log(filename) {
  mkdirSync(path.dirname(filename), { recursive: true })
  let descriptor
  let invalid = false
  try {
    descriptor = openSync(filename, 'r')
    const decoder = new TextDecoder('utf-8', { fatal: true })
    const bytes = Buffer.alloc(64 * 1024)
    let count
    try {
      while ((count = readSync(descriptor, bytes)) > 0) {
        decoder.decode(bytes.subarray(0, count), { stream: true })
      }
      decoder.decode()
    } catch (error) {
      if (!(error instanceof TypeError)) throw error
      invalid = true
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  } finally {
    if (descriptor !== undefined) closeSync(descriptor)
  }
  if (!invalid) return undefined
  const archive = `${filename}.legacy-${randomUUID()}`
  renameSync(filename, archive)
  return archive
}
