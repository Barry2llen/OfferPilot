import type { spawnSync } from 'node:child_process'

export function isProcessAlive(pid: number, kill?: typeof process.kill): boolean
export function terminateProcessTree(pid: number, options?: {
  platform?: NodeJS.Platform
  kill?: typeof process.kill
  run?: typeof spawnSync
  report?: (message: string) => void
  group?: boolean
}): boolean
