import { access, cp, mkdir, readFile, rm } from 'node:fs/promises'
import { constants } from 'node:fs'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { assertLinuxX64, assertSelfContainedSymlinks, prepareLinuxLibraries } from './linux-libraries.mjs'

const electronRoot = fileURLToPath(new URL('..', import.meta.url))
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

if (process.platform === 'linux') {
  assertLinuxX64(await readFile(path.join(distDir, executableName)), executableName)
}

await rm(outputDir, { recursive: true, force: true })
await mkdir(path.dirname(outputDir), { recursive: true })
await cp(distDir, outputDir, { recursive: true, verbatimSymlinks: true })

if (process.platform === 'linux') {
  await access(path.join(outputDir, executableName), constants.X_OK)
  await prepareLinuxLibraries(outputDir, path.join(electronRoot, 'resources', 'library-cache'))
  await assertSelfContainedSymlinks(outputDir)
}

console.log(`Prepared backend bundle at ${outputDir}`)
