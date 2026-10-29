import { readFile, writeFile } from 'node:fs/promises'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const repositoryRoot = fileURLToPath(new URL('../..', import.meta.url))
const packages = ['package.json', 'frontend/package.json', 'electron/package.json']

export function validateVersion(version) {
  if (typeof version !== 'string' || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)) {
    throw new Error(`Version must use X.Y.Z without a leading v: ${version}`)
  }
  return version
}

export async function checkVersion(root = repositoryRoot, expected) {
  const records = await Promise.all(packages.map(async file => [file, JSON.parse(await readFile(path.join(root, file), 'utf8'))]))
  const version = validateVersion(expected ?? records[0][1].version)
  for (const [file, record] of records) {
    if (record.version !== version) throw new Error(`${file} has version ${record.version}, expected ${version}.`)
  }
  const translations = await readFile(path.join(root, 'frontend/app/lib/i18n.ts'), 'utf8')
  const labels = [...translations.matchAll(/OfferPilot v(\d+\.\d+\.\d+)/g)]
  if (labels.length !== 2 || labels.some(match => match[1] !== version)) {
    throw new Error(`Expected two sidebar labels synchronized to ${version}.`)
  }
  return version
}

export function nextVersion(version, action) {
  validateVersion(version)
  const parts = version.split('.').map(BigInt)
  const index = { 'bump-major': 0, 'bump-minor': 1, 'bump-patch': 2 }[action]
  if (index === undefined) throw new Error(`Unsupported release action: ${action}`)
  parts[index] += 1n
  for (let i = index + 1; i < parts.length; i++) parts[i] = 0n
  return parts.join('.')
}

export async function bumpVersion(action, root = repositoryRoot) {
  const previous = await checkVersion(root)
  const version = nextVersion(previous, action)
  for (const file of packages) {
    const absolute = path.join(root, file)
    const record = JSON.parse(await readFile(absolute, 'utf8'))
    record.version = version
    await writeFile(absolute, `${JSON.stringify(record, null, 2)}\n`)
  }
  const file = path.join(root, 'frontend/app/lib/i18n.ts')
  const translations = await readFile(file, 'utf8')
  await writeFile(file, translations.replace(/OfferPilot v\d+\.\d+\.\d+/g, `OfferPilot v${version}`))
  await checkVersion(root, version)
  return version
}

export function checkReleaseSupport(root, platforms) {
  for (const folder of ['frontend', 'electron']) {
    if (!existsSync(path.join(root, folder, 'pnpm-lock.yaml'))) {
      throw new Error(`Release tag lacks ${folder}/pnpm-lock.yaml. Prepare a new release with pnpm support.`)
    }
  }
  if (platforms.includes('linux')) {
    const pkg = JSON.parse(readFileSync(path.join(root, 'electron/package.json'), 'utf8'))
    if (!pkg.scripts?.['build:linux'] || !existsSync(path.join(root, 'electron/scripts/smoke-linux.mjs'))) {
      throw new Error('Release tag predates Linux packaging support. Prepare a new release; tags are immutable.')
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const [command, value] = process.argv.slice(2)
    if (command === 'check') console.log(await checkVersion(repositoryRoot, value || undefined))
    else if (command === 'bump') console.log(await bumpVersion(value))
    else if (command === 'support') checkReleaseSupport(repositoryRoot, value.split(','))
    else throw new Error('Usage: release-version.mjs check [X.Y.Z] | bump bump-patch|bump-minor|bump-major | support windows,linux')
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}
