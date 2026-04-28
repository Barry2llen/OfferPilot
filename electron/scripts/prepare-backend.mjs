import { cp, mkdir, rm } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import path from 'node:path'

const electronRoot = process.cwd()
const distDir = path.join(
  electronRoot,
  'resources',
  'backend-build',
  'dist',
  'offer-pilot-api',
)
const outputDir = path.join(electronRoot, 'resources', 'backend', 'offer-pilot-api')
const executableName = process.platform === 'win32' ? 'offer-pilot-api.exe' : 'offer-pilot-api'

if (!existsSync(path.join(distDir, executableName))) {
  throw new Error(`PyInstaller backend output not found: ${distDir}`)
}

await rm(outputDir, { recursive: true, force: true })
await mkdir(path.dirname(outputDir), { recursive: true })
await cp(distDir, outputDir, { recursive: true })

console.log(`Prepared backend bundle at ${outputDir}`)
