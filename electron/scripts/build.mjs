import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const electronRoot = fileURLToPath(new URL('..', import.meta.url))

export function assertBuildHost(target, platform = process.platform, arch = process.arch) {
  const expected = { linux: 'linux', windows: 'win32' }[target]
  if (!expected || platform !== expected || arch !== 'x64') {
    throw new Error(`Cannot build ${target} x64 on ${platform}/${arch}. Use a native ${target} x64 host.`)
  }
}

export function resolveProject(folder, env = process.env) {
  const override = env[`OFFER_PILOT_${folder.toUpperCase()}_DIR`]
  const root = override ? path.resolve(override) : path.resolve(electronRoot, '..', folder)
  const marker = folder === 'backend' ? 'pyproject.toml' : 'package.json'
  if (!existsSync(path.join(root, marker))) throw new Error(`Cannot locate ${folder}: ${root}`)
  return root
}

function run(command, args, cwd = electronRoot, env = process.env) {
  const result = spawnSync(command, args, { cwd, stdio: 'inherit', env })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`${command} failed (exit ${result.status}, signal ${result.signal}).`)
}

export function pnpmInvocation(cli, node = process.execPath) {
  if (!cli || !/pnpm/i.test(cli)) throw new Error('Run builds through pnpm 12.15.0.')
  return /\.(?:cjs|mjs|js)$/i.test(cli)
    ? { command: node, prefix: [cli] }
    : { command: cli, prefix: [] }
}

function pnpm(args, cwd = electronRoot) {
  const cli = process.env.npm_execpath
  const { command, prefix } = pnpmInvocation(cli)
  run(command, [...prefix, ...args], cwd)
}

export function build(target = process.platform === 'win32' ? 'windows' : process.platform, args = []) {
  if (args.length) throw new Error('Build commands accept no extra flags. Publication belongs to the Release workflow.')
  if (!['frontend', 'backend'].includes(target)) assertBuildHost(target)
  else if (target === 'backend') assertBuildHost(process.platform === 'win32' ? 'windows' : process.platform)

  if (target !== 'backend') {
    pnpm(['run', 'build'], resolveProject('frontend'))
    run(process.execPath, ['scripts/prepare-frontend.mjs'])
  }
  if (target === 'frontend') return

  const backend = resolveProject('backend')
  run('uv', [
    'run', '--frozen', '--all-groups', '--managed-python', '--python', '3.13', '--project', backend, 'pyinstaller',
    path.join(backend, 'packaging', 'offer_pilot_api.spec'), '--noconfirm', '--clean',
    '--distpath', path.join(electronRoot, 'resources/backend-build/dist'),
    '--workpath', path.join(electronRoot, 'resources/backend-build/build'),
  ], electronRoot, {
    ...process.env,
    UV_PROJECT_ENVIRONMENT: path.join(electronRoot, 'resources/backend-build/venv'),
  })
  run(process.execPath, ['scripts/prepare-backend.mjs'])
  if (target === 'backend') return

  pnpm(['run', 'build:electron'])
  pnpm(['exec', 'electron-builder', target === 'linux' ? '--linux' : '--win', '--x64', '--publish', 'never', ...args])
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    build(process.argv[2], process.argv.slice(3))
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}
