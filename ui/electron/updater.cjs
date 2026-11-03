const { app } = require('electron')
const path = require('node:path')
const fs = require('node:fs')

// Update feed URL: env GAMEBOT_UPDATE_URL, or {"url": "..."} in <userData>/update.json.
function feedUrl() {
  if (process.env.GAMEBOT_UPDATE_URL) return process.env.GAMEBOT_UPDATE_URL
  try {
    return JSON.parse(fs.readFileSync(path.join(app.getPath('userData'), 'update.json'), 'utf8')).url
  } catch {
    return undefined
  }
}

function checkForUpdates() {
  const url = feedUrl()
  if (!app.isPackaged || !url) return
  const { autoUpdater } = require('electron-updater')
  autoUpdater.setFeedURL({ provider: 'generic', url })
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.on('error', (e) => console.error('update check failed:', e.message))
  autoUpdater.checkForUpdatesAndNotify().catch((e) => console.error('update check failed:', e.message))
}

module.exports = { checkForUpdates }
