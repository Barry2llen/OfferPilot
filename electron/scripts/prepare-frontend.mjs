import { cp, mkdir, readdir, rm } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import path from 'node:path'

const electronRoot = process.cwd()
const frontendRoot = resolveProjectDir(
  process.env.OFFER_PILOT_FRONTEND_DIR,
  'frontend',
  'package.json',
)
const standaloneDir = path.join(frontendRoot, '.next', 'standalone')
const staticDir = path.join(frontendRoot, '.next', 'static')
const publicDir = path.join(frontendRoot, 'public')
const outputDir = path.join(electronRoot, 'resources', 'frontend')

if (!existsSync(path.join(standaloneDir, 'server.js'))) {
  throw new Error(`Next standalone output not found: ${standaloneDir}`)
}

await rm(outputDir, { recursive: true, force: true })
await mkdir(outputDir, { recursive: true })
await cp(standaloneDir, outputDir, { recursive: true })
await cp(staticDir, path.join(outputDir, '.next', 'static'), { recursive: true })

if (existsSync(publicDir)) {
  await cp(publicDir, path.join(outputDir, 'public'), { recursive: true })
}

for (const fileName of await readdir(outputDir)) {
  if (fileName === '.env' || fileName.startsWith('.env.')) {
    await rm(path.join(outputDir, fileName), { force: true })
  }
}

console.log(`Prepared Next.js standalone bundle at ${outputDir}`)

function resolveProjectDir(envValue, folderName, markerFile) {
  const candidates = [
    envValue ? path.resolve(envValue) : '',
    path.resolve(electronRoot, '..', folderName),
  ].filter(Boolean)

  for (const candidate of candidates) {
    if (existsSync(path.join(candidate, markerFile))) {
      return candidate
    }
  }

  throw new Error(`Cannot locate ${folderName}. Set OFFER_PILOT_FRONTEND_DIR.`)
}
