import path from 'node:path'
import { fileURLToPath } from 'node:url'

export function releasePlatforms(action) {
  const platforms = {
    automatic: ['windows', 'linux'],
    'build-all': ['windows', 'linux'],
    'build-windows': ['windows'],
    'build-linux': ['linux'],
  }[action]
  if (!platforms) throw new Error(`Unsupported build action: ${action}`)
  return platforms
}

export function assertPublishable(platforms, results) {
  if (!platforms.length || new Set(platforms).size !== platforms.length
    || platforms.some(platform => !['windows', 'linux'].includes(platform))) {
    throw new Error('Expected Windows and/or Linux release platforms.')
  }
  const required = platforms.flatMap(platform => platform === 'linux' ? ['linux', 'verifyLinux'] : ['windows'])
  for (const job of required) {
    if (results[job] !== 'success') throw new Error(`Release blocked: ${job} result is ${results[job] ?? 'missing'}.`)
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv[2] === 'platforms') {
      console.log(releasePlatforms(process.argv[3]).join(','))
    } else assertPublishable((process.env.RELEASE_PLATFORMS ?? '').split(','), {
      windows: process.env.WINDOWS_RESULT,
      linux: process.env.LINUX_RESULT,
      verifyLinux: process.env.VERIFY_LINUX_RESULT,
    })
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}
