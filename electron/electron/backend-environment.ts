import { existsSync } from 'node:fs'
import path from 'node:path'
import { pythonEnvironment } from '../scripts/runtime-output.mjs'

export function backendEnvironment(
  executable: string,
  platform = process.platform,
  environment: NodeJS.ProcessEnv = process.env,
): NodeJS.ProcessEnv {
  if (platform !== 'linux') return { ...pythonEnvironment }
  const compat = path.join(path.dirname(executable), 'compat')
  for (const library of ['libicudata.so.66', 'libicui18n.so.66', 'libicuuc.so.66', 'libssl.so.1.1', 'libcrypto.so.1.1']) {
    if (!existsSync(path.join(compat, library))) throw new Error(`Packaged compatibility library not found: ${library}`)
  }
  return {
    ...pythonEnvironment,
    LD_LIBRARY_PATH: [compat, environment.LD_LIBRARY_PATH].filter(Boolean).join(':'),
  }
}
