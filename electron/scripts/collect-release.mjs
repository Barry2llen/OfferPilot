import { createHash } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { cp, mkdir, rm, stat, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { validateVersion } from './release-version.mjs'

export async function sha256File(file) {
  const hash = createHash('sha256')
  for await (const bytes of createReadStream(file)) hash.update(bytes)
  return hash.digest('hex')
}

export function assetNames(platform, version) {
  validateVersion(version)
  const prefix = `OfferPilot-${platform === 'windows' ? 'Windows' : 'Linux'}-x64-v${version}`
  if (platform === 'windows') return [`${prefix}.exe`]
  if (platform === 'linux') return [`${prefix}.AppImage`, `${prefix}.deb`, `${prefix}.sha256`]
  throw new Error(`Unsupported artifact platform: ${platform}`)
}

export async function collectAssets(platform, version, electronRoot = fileURLToPath(new URL('..', import.meta.url))) {
  const names = assetNames(platform, version)
  const release = path.join(electronRoot, 'release', version)
  const output = path.join(release, 'assets', platform)
  const payloads = names.filter(name => !name.endsWith('.sha256'))
  const sources = payloads.map(name => platform === 'windows' ? `OfferPilot-Windows-${version}-Setup.exe` : name)
  for (const file of sources) {
    const info = await stat(path.join(release, file)).catch(() => null)
    if (!info?.isFile() || !info.size) throw new Error(`Required release installer is missing or empty: ${file}`)
  }
  await rm(output, { recursive: true, force: true })
  await mkdir(output, { recursive: true })
  for (let i = 0; i < sources.length; i++) await cp(path.join(release, sources[i]), path.join(output, payloads[i]))
  if (platform === 'linux') {
    const lines = await Promise.all(payloads.map(async name => `${await sha256File(path.join(output, name))}  ${name}`))
    await writeFile(path.join(output, names.at(-1)), `${lines.join('\n')}\n`)
  }
  return output
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    console.log(await collectAssets(process.argv[2], process.argv[3]))
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}
