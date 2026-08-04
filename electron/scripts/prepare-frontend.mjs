import { cp, mkdir, rm } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import path from 'node:path'

const electronRoot = process.cwd()
const frontendRoot = resolveProjectDir(
  process.env.OFFER_PILOT_FRONTEND_DIR,
  'frontend',
  'package.json',
)
const distDir = path.join(frontendRoot, 'dist')
const outputDir = path.join(electronRoot, 'resources', 'frontend')

if (!existsSync(path.join(distDir, 'index.html'))) {
  throw new Error(`Vite frontend build not found: ${distDir}`)
}

await rm(outputDir, { recursive: true, force: true })
await mkdir(outputDir, { recursive: true })
await cp(distDir, outputDir, { recursive: true })

console.log(`Prepared Vite frontend bundle at ${outputDir}`)

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
