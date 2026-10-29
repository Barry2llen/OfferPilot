import type { Readable, Transform, Writable } from 'node:stream'

export const pythonEnvironment: Readonly<{
  PYTHONUTF8: string
  PYTHONIOENCODING: string
  PYTHONUNBUFFERED: string
}>
export class Utf8Decoder {
  constructor(label?: string)
  write(chunk: Uint8Array | string, final?: boolean): string
  end(): string
}
export function forwardUtf8(source: Readable, destination: Writable, label?: string, onText?: (text: string) => void): Transform
export function prepareUtf8Log(filename: string): string | undefined
