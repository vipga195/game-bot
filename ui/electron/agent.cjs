const { spawn } = require('node:child_process')
const path = require('node:path')
const fs = require('node:fs')

let child = null

function agentCommand(app) {
  if (app.isPackaged) {
    const exe = process.platform === 'win32' ? 'gamebot-agent.exe' : 'gamebot-agent'
    return { cmd: path.join(process.resourcesPath, 'agent', exe), args: [], cwd: process.resourcesPath }
  }
  // dev: run the agent from source with uv
  return { cmd: 'uv', args: ['run', 'python', '-m', 'gamebot'], cwd: path.join(__dirname, '..', '..', 'agent') }
}

function startAgent(app) {
  if (process.env.GAMEBOT_NO_AGENT === '1' || child) return
  const { cmd, args, cwd } = agentCommand(app)
  if (path.isAbsolute(cmd) && !fs.existsSync(cmd)) {
    console.error(`agent binary not found: ${cmd}`)
    return
  }
  child = spawn(cmd, args, { cwd, stdio: 'inherit', windowsHide: true })
  child.on('error', (e) => console.error('agent failed to start:', e.message))
  child.on('exit', () => { child = null })
}

function stopAgent() {
  if (!child) return
  if (process.platform === 'win32') {
    // kill the whole tree (uv/python children)
    spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true })
  } else {
    child.kill('SIGTERM')
  }
  child = null
}

module.exports = { startAgent, stopAgent }
