// Electron 43 exposes an explicit installer instead of an npm postinstall hook.
// Verification jobs launch the packaged runtime and can skip this extra download.
if (process.env.ELECTRON_SKIP_BINARY_DOWNLOAD !== '1') await import('electron/install.js')
