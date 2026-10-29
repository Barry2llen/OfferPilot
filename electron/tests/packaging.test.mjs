import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { createHash } from 'node:crypto'
import { assertBuildHost, pnpmInvocation } from '../scripts/build.mjs'
import { assertLinuxX64, assertSelfContainedSymlinks, libraries, verifyChecksum } from '../scripts/linux-libraries.mjs'
import { backendEnvironment } from '../electron/backend-environment.ts'
import { pythonEnvironment } from '../scripts/runtime-output.mjs'
import { bumpVersion, checkReleaseSupport, checkVersion, nextVersion } from '../scripts/release-version.mjs'
import { collectAssets } from '../scripts/collect-release.mjs'
import { publishRelease, validateAssets } from '../scripts/publish-release.mjs'
import { assertPublishable, releasePlatforms } from '../scripts/release-policy.mjs'

async function temporary(t) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'offerpilot-test-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  return directory
}

test('native builds reject wrong OS and architecture before packaging', () => {
  assert.doesNotThrow(() => assertBuildHost('linux', 'linux', 'x64'))
  assert.doesNotThrow(() => assertBuildHost('windows', 'win32', 'x64'))
  for (const [target, host, arch] of [['linux', 'win32', 'x64'], ['linux', 'linux', 'arm64'], ['windows', 'linux', 'x64'], ['darwin', 'darwin', 'x64']]) {
    assert.throws(() => assertBuildHost(target, host, arch), /native/)
  }
})

test('both standalone pnpm and Node-based pnpm launch through the correct interpreter', () => {
  assert.deepEqual(pnpmInvocation('/tools/pnpm', '/tools/node'), { command: '/tools/pnpm', prefix: [] })
  assert.deepEqual(pnpmInvocation('/tools/pnpm.cjs', '/tools/node'), { command: '/tools/node', prefix: ['/tools/pnpm.cjs'] })
  assert.deepEqual(pnpmInvocation('C:\\tools\\pnpm.exe', 'node.exe'), { command: 'C:\\tools\\pnpm.exe', prefix: [] })
  assert.throws(() => pnpmInvocation('/tools/npm.js'), /pnpm/)
})

test('compatibility archives reject corruption and wrong binary architectures', () => {
  const bytes = Buffer.from('verified archive')
  const digest = createHash('sha256').update(bytes).digest('hex')
  assert.doesNotThrow(() => verifyChecksum(bytes, digest, 'archive'))
  assert.throws(() => verifyChecksum(Buffer.from('corrupt'), digest, 'archive'), /SHA-256 mismatch/)
  const elf = Buffer.alloc(64)
  elf.write('7f454c46', 'hex')
  elf[4] = 2
  elf[5] = 1
  elf.writeUInt16LE(62, 18)
  assert.doesNotThrow(() => assertLinuxX64(elf, 'backend'))
  elf.writeUInt16LE(183, 18)
  assert.throws(() => assertLinuxX64(elf, 'backend'), /x86-64/)
  assert.throws(() => assertLinuxX64(Buffer.from('MZ'), 'backend'), /ELF/)
})

test('Linux bundles keep relative symlinks and reject build-machine paths', { skip: process.platform === 'win32' }, async t => {
  const root = await temporary(t)
  await mkdir(path.join(root, 'bundle/lib'), { recursive: true })
  await writeFile(path.join(root, 'bundle/lib/native.so'), 'binary')
  await symlink('lib/native.so', path.join(root, 'bundle/native.so'))
  await assertSelfContainedSymlinks(path.join(root, 'bundle'))
  await writeFile(path.join(root, 'outside.so'), 'host binary')
  await symlink('../outside.so', path.join(root, 'bundle/host.so'))
  await assert.rejects(assertSelfContainedSymlinks(path.join(root, 'bundle')), /escapes the bundle/)
})

test('Linux libraries are scoped to the backend environment and missing libraries fail', async t => {
  const root = await temporary(t)
  const executable = path.join(root, 'offer-pilot-api')
  const original = { LD_LIBRARY_PATH: '/system-libraries', OTHER: 'unchanged' }
  assert.throws(() => backendEnvironment(executable, 'linux', original), /compatibility library/)
  const compat = path.join(root, 'compat')
  await mkdir(compat)
  for (const library of libraries) for (const file of library.files) await writeFile(path.join(compat, file), 'library')
  assert.deepEqual(backendEnvironment(executable, 'linux', original), {
    ...pythonEnvironment, LD_LIBRARY_PATH: `${compat}:/system-libraries`,
  })
  assert.deepEqual(original, { LD_LIBRARY_PATH: '/system-libraries', OTHER: 'unchanged' })
  assert.deepEqual(backendEnvironment(executable, 'win32', original), pythonEnvironment)
})

async function versionFixture(t) {
  const root = await temporary(t)
  for (const directory of ['.', 'frontend', 'electron']) {
    await mkdir(path.join(root, directory), { recursive: true })
    await writeFile(path.join(root, directory, 'package.json'), JSON.stringify({ name: directory, version: '1.2.3' }))
  }
  await mkdir(path.join(root, 'frontend/app/lib'), { recursive: true })
  await writeFile(path.join(root, 'frontend/app/lib/i18n.ts'), 'zh: "OfferPilot v1.2.3", en: "OfferPilot v1.2.3"')
  return root
}

test('version bumps synchronize every package and both locale labels without npm lockfiles', async t => {
  const root = await versionFixture(t)
  assert.equal(await bumpVersion('bump-minor', root), '1.3.0')
  assert.equal(await checkVersion(root, '1.3.0'), '1.3.0')
  assert.equal(nextVersion('1.2.3', 'bump-major'), '2.0.0')
  assert.equal(nextVersion('1.2.3', 'bump-patch'), '1.2.4')
  await writeFile(path.join(root, 'electron/package.json'), JSON.stringify({ version: '1.3.1' }))
  await assert.rejects(checkVersion(root), /expected 1.3.0/)
})

test('inconsistent translations and invalid versions stop release preparation', async t => {
  const root = await versionFixture(t)
  await writeFile(path.join(root, 'frontend/app/lib/i18n.ts'), 'OfferPilot v1.2.3')
  await assert.rejects(bumpVersion('bump-patch', root), /two sidebar labels/)
  assert.equal(JSON.parse(await readFile(path.join(root, 'package.json'))).version, '1.2.3')
  assert.throws(() => nextVersion('v1.2.3', 'bump-patch'), /X.Y.Z/)
  assert.throws(() => nextVersion('1.2.3', 'arbitrary'), /Unsupported/)
})

test('historical tags without lockfiles or Linux support fail clearly', async t => {
  const root = await versionFixture(t)
  assert.throws(() => checkReleaseSupport(root, ['linux']), /pnpm-lock/)
  for (const directory of ['frontend', 'electron']) await writeFile(path.join(root, directory, 'pnpm-lock.yaml'), 'lockfileVersion: 9')
  assert.throws(() => checkReleaseSupport(root, ['linux']), /predates Linux/)
})

test('only complete validated installers are collected, verified and repeatable', async t => {
  const root = await temporary(t)
  const release = path.join(root, 'release/1.2.3')
  await mkdir(release, { recursive: true })
  await assert.rejects(collectAssets('linux', '1.2.3', root), /missing or empty/)
  for (const ext of ['AppImage', 'deb']) await writeFile(path.join(release, `OfferPilot-Linux-x64-v1.2.3.${ext}`), `installer ${ext}`)
  const output = await collectAssets('linux', '1.2.3', root)
  assert.equal((await validateAssets(output, '1.2.3', ['linux'])).length, 3)
  assert.equal(await collectAssets('linux', '1.2.3', root), output)
  await writeFile(path.join(output, 'OfferPilot-Linux-x64-v1.2.3.deb'), 'tampered')
  await assert.rejects(validateAssets(output, '1.2.3', ['linux']), /checksum manifest/)
})

test('release gate requires all selected builds and both Linux verification jobs', () => {
  const automatic = releasePlatforms('automatic')
  const success = { windows: 'success', linux: 'success', verifyLinux: 'success' }
  assert.doesNotThrow(() => assertPublishable(automatic, success))
  for (const name of Object.keys(success)) {
    for (const status of ['failure', 'cancelled', 'skipped', undefined]) {
      assert.throws(() => assertPublishable(automatic, { ...success, [name]: status }), /Release blocked/)
    }
  }
  assert.doesNotThrow(() => assertPublishable(releasePlatforms('build-windows'), { windows: 'success' }))
  assert.doesNotThrow(() => assertPublishable(releasePlatforms('build-linux'), { linux: 'success', verifyLinux: 'success' }))
  assert.throws(() => releasePlatforms('bump-patch'), /Unsupported/)
  assert.throws(() => assertPublishable([], success), /Expected/)
  assert.throws(() => assertPublishable(['linux', 'linux'], success), /Expected/)
})

async function publicationFixture(t) {
  const root = await temporary(t)
  await mkdir(path.join(root, 'release/1.2.3'), { recursive: true })
  for (const ext of ['AppImage', 'deb']) await writeFile(path.join(root, 'release/1.2.3', `OfferPilot-Linux-x64-v1.2.3.${ext}`), ext)
  const output = await collectAssets('linux', '1.2.3', root)
  await writeFile(path.join(output, 'OfferPilot-Windows-x64-v1.2.3.exe'), 'Windows installer')
  return {
    RELEASE_VERSION: '1.2.3', RELEASE_PLATFORMS: 'windows,linux', GITHUB_REPOSITORY: 'example/OfferPilot',
    RELEASE_ASSETS: output, WINDOWS_RESULT: 'success', LINUX_RESULT: 'success', VERIFY_LINUX_RESULT: 'success',
  }
}

test('new releases upload all assets to a draft before becoming public', async t => {
  const environment = await publicationFixture(t)
  const calls = []
  await publishRelease(environment, args => { calls.push(args); return args[0] === 'api' ? null : '' })
  assert.deepEqual(calls.map(args => args.slice(0, 2)), [['api', 'repos/example/OfferPilot/releases/tags/v1.2.3'], ['release', 'create'], ['release', 'upload'], ['release', 'edit']])
  assert.ok(calls[1].includes('--draft'))
  assert.equal(calls[2].filter(arg => /\.(exe|AppImage|deb|sha256)$/.test(arg)).length, 4)
  assert.ok(calls[3].includes('--draft=false'))
})

test('failed required jobs prevent all GitHub publication calls', async t => {
  const environment = await publicationFixture(t)
  await assert.rejects(publishRelease({ ...environment, VERIFY_LINUX_RESULT: 'failure' }, () => assert.fail('GitHub must not be called')), /Release blocked/)
})

test('an upload failure leaves the new release unpublished', async t => {
  const environment = await publicationFixture(t)
  const calls = []
  await assert.rejects(publishRelease(environment, args => {
    calls.push(args)
    if (args[1] === 'upload') throw new Error('Upload failed')
    return args[0] === 'api' ? null : ''
  }), /Upload failed/)
  assert.equal(calls.some(args => args[1] === 'edit'), false)
})

test('single-platform rebuilds replace only selected assets in an existing published release', async t => {
  const environment = { ...await publicationFixture(t), RELEASE_PLATFORMS: 'linux', WINDOWS_RESULT: 'skipped' }
  const calls = []
  const command = args => { calls.push(args); return args[0] === 'api' ? '{"draft":false}' : '' }
  await publishRelease(environment, command)
  await publishRelease(environment, command)
  const uploads = calls.filter(args => args[1] === 'upload')
  assert.equal(uploads.length, 2)
  assert.equal(uploads.some(args => args.some(arg => arg.endsWith('.exe'))), false)
  assert.equal(calls.some(args => ['create', 'edit'].includes(args[1])), false)
  for (const current of [null, '{"draft":true}']) {
    await assert.rejects(publishRelease(environment, args => args[0] === 'api' ? current : assert.fail('Must not modify an incomplete release')), /existing published Release/)
  }
})
