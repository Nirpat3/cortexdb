const { execSync, spawn } = require('child_process');
const net = require('net');
const path = require('path');
const fs = require('fs');

const PREFERRED_PORT = 3400;
const DASHBOARD_DIR = path.resolve(__dirname, '..');

// ── Helpers ──────────────────────────────────────────────

function log(tag, msg) {
  const colors = { INFO: '\x1b[36m', OK: '\x1b[32m', WARN: '\x1b[33m', ERR: '\x1b[31m' };
  console.log(`${colors[tag] || ''}  [${tag}]\x1b[0m ${msg}`);
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const client = net.createConnection({ port, host: '127.0.0.1' }, () => {
      client.destroy();
      resolve(false); // port in use
    });
    client.on('error', () => resolve(true)); // port free
  });
}

async function findFreePort(start) {
  for (let p = start; p < start + 100; p++) {
    if (await isPortFree(p)) return p;
  }
  throw new Error('No free port found');
}

function ensureDeps() {
  const nmPath = path.join(DASHBOARD_DIR, 'node_modules');
  if (!fs.existsSync(nmPath)) {
    log('INFO', 'Installing dependencies (first run)...');
    execSync('npm install', { cwd: DASHBOARD_DIR, stdio: 'inherit' });
    log('OK', 'Dependencies installed.');
  }
}

// ── Main ─────────────────────────────────────────────────

async function main() {
  console.log('');
  console.log('  \x1b[36m╔══════════════════════════════════════════╗\x1b[0m');
  console.log('  \x1b[36m║\x1b[0m   \x1b[1mCortexDB Dashboard\x1b[0m  v4.0.0             \x1b[36m║\x1b[0m');
  console.log('  \x1b[36m║\x1b[0m   The Consciousness-Inspired Database    \x1b[36m║\x1b[0m');
  console.log('  \x1b[36m╚══════════════════════════════════════════╝\x1b[0m');
  console.log('');

  // 1. Ensure dependencies
  ensureDeps();

  // 2. Find available port
  log('INFO', `Checking port ${PREFERRED_PORT}...`);
  const port = await findFreePort(PREFERRED_PORT);
  if (port !== PREFERRED_PORT) {
    log('WARN', `Port ${PREFERRED_PORT} is in use. Using port ${port} instead.`);
  } else {
    log('OK', `Port ${port} is available.`);
  }

  // 3. Write port to file so the batch script can read it
  fs.writeFileSync(path.join(DASHBOARD_DIR, '.port'), String(port));

  // 4. Start Next.js dev server
  log('INFO', `Starting dashboard on http://localhost:${port} ...`);
  console.log('');

  const child = spawn('npx', ['next', 'dev', '--port', String(port)], {
    cwd: DASHBOARD_DIR,
    stdio: 'inherit',
    shell: true,
    env: { ...process.env, NODE_ENV: 'development' },
  });

  child.on('error', (err) => {
    log('ERR', `Failed to start: ${err.message}`);
    process.exit(1);
  });

  child.on('exit', (code) => {
    if (code !== 0) log('ERR', `Dashboard exited with code ${code}`);
    // Clean up port file
    try { fs.unlinkSync(path.join(DASHBOARD_DIR, '.port')); } catch {}
    process.exit(code || 0);
  });

  // Graceful shutdown
  const cleanup = () => {
    log('INFO', 'Shutting down...');
    child.kill('SIGTERM');
    try { fs.unlinkSync(path.join(DASHBOARD_DIR, '.port')); } catch {}
  };
  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);
}

main().catch((err) => {
  log('ERR', err.message);
  process.exit(1);
});
