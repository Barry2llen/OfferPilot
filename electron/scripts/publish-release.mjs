import { spawnSync } from 'node:child_process'
import { readFile, stat } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { assetNames, sha256File } from './collect-release.mjs'
import { validateVersion } from './release-version.mjs'
import { assertPublishable } from './release-policy.mjs'

export async function validateAssets(directory, version, platforms) {
  const files = platforms.flatMap(platform => assetNames(platform, version))
  for (const name of files) {
    const info = await stat(path.join(directory, name)).catch(() => null)
    if (!info?.isFile() || !info.size) throw new Error(`Missing release asset: ${name}`)
  }
  if (platforms.includes('linux')) {
    const names = assetNames('linux', version)
    const expected = (await Promise.all(names.slice(0, 2).map(async name => `${await sha256File(path.join(directory, name))}  ${name}`))).join('\n') + '\n'
    if (await readFile(path.join(directory, names[2]), 'utf8') !== expected) throw new Error('Linux installer checksum manifest does not match the artifacts.')
  }
  return files.map(name => path.join(directory, name))
}

function gh(args, allowMissing = false) {
  const result = spawnSync('gh', args, { encoding: 'utf8' })
  if (result.error) throw result.error
  if (result.status !== 0) {
    if (allowMissing && /HTTP 404|release not found/i.test(result.stderr)) return null
    throw new Error(`gh ${args[0]} failed: ${result.stderr}`)
  }
  return result.stdout
}

export async function publishRelease(environment = process.env, command = gh) {
  const version = validateVersion(environment.RELEASE_VERSION)
  const platforms = (environment.RELEASE_PLATFORMS ?? '').split(',')
  assertPublishable(platforms, {
    windows: environment.WINDOWS_RESULT,
    linux: environment.LINUX_RESULT,
    verifyLinux: environment.VERIFY_LINUX_RESULT,
  })
  const repository = environment.GITHUB_REPOSITORY
  if (!repository || !/^[\w.-]+\/[\w.-]+$/.test(repository)) throw new Error('GITHUB_REPOSITORY is required.')
  const files = await validateAssets(path.resolve(environment.RELEASE_ASSETS ?? 'release-assets'), version, platforms)
  const tag = `v${version}`
  const current = command(['api', `repos/${repository}/releases/tags/${tag}`], true)
  const draft = current === null || JSON.parse(current).draft
  if (draft && platforms.length !== 2) throw new Error('Single-platform rebuilds require an existing published Release. Use build-all to complete a draft.')
  if (current === null) {
    command(['release', 'create', tag, '--repo', repository, '--title', tag, '--verify-tag', '--generate-notes', '--draft'])
  }
  command(['release', 'upload', tag, ...files, '--repo', repository, '--clobber'])
  if (draft) {
    // A failed upload leaves a draft; no incomplete new release becomes public.
    command(['release', 'edit', tag, '--repo', repository, '--draft=false'])
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    await publishRelease()
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}
