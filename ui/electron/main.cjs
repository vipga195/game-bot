const { app, BrowserWindow, protocol, net } = require('electron')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const { startAgent, stopAgent } = require('./agent.cjs')
const { checkForUpdates } = require('./updater.cjs')

const DIST = path.join(__dirname, '..', 'dist')

protocol.registerSchemesAsPrivileged([{ scheme: 'app', privileges: { standard: true, secure: true } }])

function createWindow() {
  const win = new BrowserWindow({ width: 1280, height: 800, webPreferences: { contextIsolation: true } })
  // GAMEBOT_UI_URL points to a Vite dev server; otherwise load the built UI (origin app://ui is allowed by agent CORS)
  win.loadURL(process.env.GAMEBOT_UI_URL || 'app://ui/index.html')
}

if (!app.requestSingleInstanceLock()) app.quit()

app.whenReady().then(() => {
  protocol.handle('app', (req) => {
    const rel = decodeURIComponent(new URL(req.url).pathname)
    const file = path.normalize(path.join(DIST, rel))
    if (!file.startsWith(DIST)) return new Response('forbidden', { status: 403 })
    return net.fetch(pathToFileURL(file).toString())
  })
  startAgent(app)
  createWindow()
  checkForUpdates()
})

app.on('window-all-closed', () => app.quit())
app.on('before-quit', stopAgent)
