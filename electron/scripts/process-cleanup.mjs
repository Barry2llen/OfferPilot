import { spawnSync } from 'node:child_process'

export function isProcessAlive(pid, kill = process.kill) {
  try {
    kill(pid, 0)
    return true
  } catch (error) {
    return error.code !== 'ESRCH'
  }
}

export function terminateProcessTree(pid, {
  platform = process.platform,
  kill = process.kill,
  run = spawnSync,
  report = message => console.error(message),
  group = false,
  force = false,
} = {}) {
  if (!Number.isSafeInteger(pid) || pid <= 0) throw new Error('Invalid managed process PID')
  const target = platform !== 'win32' && group && isProcessAlive(-pid, kill) ? -pid : pid
  if (!isProcessAlive(target, kill)) return true
  if (platform === 'win32') {
    const result = run('taskkill.exe', ['/pid', String(pid), '/t', '/f'], {
      stdio: 'ignore', windowsHide: true, timeout: 2000,
    })
    if (!result.error && result.status === 0) return true
    if (!isProcessAlive(pid, kill)) return true
    report(`[process-cleanup] taskkill failed pid=${pid} exit=${result.status ?? 'null'} error=${result.error?.code ?? 'none'}`)
    return false
  }
  try {
    const signal = force ? 'SIGKILL' : 'SIGTERM'
    kill(target, signal)
    return true
  } catch (error) {
    if (error.code === 'ESRCH') return true
    report(`[process-cleanup] ${force ? 'SIGKILL' : 'SIGTERM'} failed pid=${pid} error=${error.code ?? 'unknown'}`)
    return false
  }
}
