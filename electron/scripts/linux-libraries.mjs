import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { cp, mkdir, mkdtemp, readFile, readdir, readlink, realpath, rename, rm, stat, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import path from 'node:path'
import os from 'node:os'

export const libraries = [
  {
    name: 'libicu66',
    version: '66.1-2ubuntu2.1',
    url: 'https://archive.ubuntu.com/ubuntu/pool/main/i/icu/libicu66_66.1-2ubuntu2.1_amd64.deb',
    sha256: '00d0de456134668f41bd9ea308a076bc0a6a805180445af8a37209d433f41efe',
    files: ['libicudata.so.66', 'libicui18n.so.66', 'libicuuc.so.66'],
  },
  {
    name: 'libssl1.1',
    version: '1.1.1f-1ubuntu2.24',
    url: 'https://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_amd64.deb',
    sha256: '7cf39d70a639017d1dd7c8d36daa2258063608688e449fddf40ffdd46f992a78',
    files: ['libssl.so.1.1', 'libcrypto.so.1.1'],
  },
]

export function verifyChecksum(bytes, expected, label) {
  const actual = createHash('sha256').update(bytes).digest('hex')
  if (actual !== expected) throw new Error(`SHA-256 mismatch for ${label}: expected ${expected}, got ${actual}`)
}

export function assertLinuxX64(bytes, label) {
  if (bytes.length < 20 || bytes.subarray(0, 4).toString('hex') !== '7f454c46'
    || bytes[4] !== 2 || bytes[5] !== 1 || bytes.readUInt16LE(18) !== 62) {
    throw new Error(`${label} must be a Linux x86-64 ELF binary.`)
  }
}

export async function assertSelfContainedSymlinks(directory) {
  const root = await realpath(directory)
  async function walk(current) {
    for (const entry of await readdir(current, { withFileTypes: true })) {
      const file = path.join(current, entry.name)
      if (entry.isSymbolicLink()) {
        const target = await readlink(file)
        const resolved = await realpath(file)
        const relative = path.relative(root, resolved)
        if (path.isAbsolute(target) || relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
          throw new Error(`Backend symlink escapes the bundle: ${file} -> ${target}`)
        }
      } else if (entry.isDirectory()) await walk(file)
    }
  }
  await walk(root)
}

async function downloadArchive(library, cache) {
  const file = path.join(cache, path.basename(library.url))
  if (existsSync(file)) {
    verifyChecksum(await readFile(file), library.sha256, file)
    return file
  }
  const response = await fetch(library.url, { signal: AbortSignal.timeout(120_000) })
  if (!response.ok) throw new Error(`Download failed: ${library.url} (HTTP ${response.status})`)
  const bytes = Buffer.from(await response.arrayBuffer())
  verifyChecksum(bytes, library.sha256, library.url)
  const temporary = `${file}.${process.pid}.tmp`
  try {
    await writeFile(temporary, bytes)
    await rename(temporary, file)
  } finally {
    await rm(temporary, { force: true })
  }
  return file
}

export async function prepareLinuxLibraries(bundleRoot, cache) {
  await mkdir(cache, { recursive: true })
  const temporary = await mkdtemp(path.join(os.tmpdir(), 'offerpilot-libraries-'))
  const output = path.join(bundleRoot, 'compat')
  try {
    await rm(output, { recursive: true, force: true })
    await mkdir(path.join(output, 'licenses'), { recursive: true })
    for (const library of libraries) {
      const archive = await downloadArchive(library, cache)
      const extracted = path.join(temporary, library.name)
      const result = spawnSync('dpkg-deb', ['--extract', archive, extracted], { encoding: 'utf8' })
      if (result.error) throw result.error
      if (result.status !== 0) throw new Error(`Cannot extract ${library.name}: ${result.stderr}`)
      for (const file of library.files) {
        const source = path.join(extracted, 'usr/lib/x86_64-linux-gnu', file)
        assertLinuxX64(await readFile(source), file)
        // Dereference the versioned symlink so every bundled SONAME is self-contained.
        await cp(source, path.join(output, file), { dereference: true })
      }
      await cp(path.join(extracted, 'usr/share/doc', library.name, 'copyright'),
        path.join(output, 'licenses', `${library.name}.copyright`))
    }
    await writeFile(path.join(output, 'manifest.json'), `${JSON.stringify(libraries, null, 2)}\n`)
  } finally {
    await rm(temporary, { recursive: true, force: true })
  }
  for (const library of libraries) {
    for (const file of library.files) {
      if (!(await stat(path.join(output, file))).size) throw new Error(`Empty compatibility library: ${file}`)
    }
  }
}
