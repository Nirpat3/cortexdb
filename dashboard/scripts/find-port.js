const net = require('net');

function isPortFree(port) {
  return new Promise((resolve) => {
    const client = net.createConnection({ port, host: '127.0.0.1' }, () => {
      // Connection succeeded — port is in use
      client.destroy();
      resolve(false);
    });
    client.on('error', () => {
      // Connection failed — port is free
      resolve(true);
    });
  });
}

async function findFreePort(startPort) {
  let port = startPort;
  while (port < startPort + 100) {
    if (await isPortFree(port)) {
      return port;
    }
    port++;
  }
  throw new Error(`No free port found between ${startPort} and ${startPort + 99}`);
}

const preferred = parseInt(process.argv[2] || '3400', 10);
findFreePort(preferred).then((port) => {
  process.stdout.write(String(port));
});
