require('dotenv').config();
const { Device, MonitoringResult } = require('./models');
const { discoverNetwork } = require('./services/discovery');
const { monitorDevices } = require('./services/monitoring');
const redis = require('./utils/redis');
const { raiseAlert } = require('./utils/alerts');
const logger = require('./utils/logger');

const CPU_THRESHOLD = parseFloat(process.env.ALERT_CPU_THRESHOLD) || 90;

class WorkerService {
  constructor() { this.isRunning = false; this.timers = []; }

  async waitForSchema(retries = 30, delayMs = 2000) {
    for (let i = 0; i < retries; i++) {
      try { await Device.findAll({ limit: 1 }); return true; }
      catch { if (i === 0) logger.info('Waiting for database schema...'); await new Promise((r) => setTimeout(r, delayMs)); }
    }
    return false;
  }

  async runMonitoring() {
    await redis.withLock('lock:monitor', 4 * 60 * 1000, async () => {
      const devices = await Device.findAll();
      if (!devices.length) return;
      logger.info(`Monitoring ${devices.length} devices...`);
      const results = await monitorDevices(devices, { maxConcurrent: 10 });
      for (const r of results) {
        const device = devices.find((d) => d.ip_address === r.ip_address);
        if (!device) continue;
        const online = r.ping || r.ssh || r.telnet || r.snmp;
        try {
          await MonitoringResult.create({
            device_id: device.id, ping: r.ping, ssh: r.ssh, telnet: r.telnet, snmp: r.snmp,
            response_time_ms: r.response_time_ms, error: r.error,
            cpu_utilization: r.metrics && r.metrics.cpu_utilization,
            memory_utilization: r.metrics && r.metrics.memory_utilization
          });
          if (device.status === 'online' && !online) {
            await raiseAlert({ device_id: device.id, severity: 'critical', type: 'device_down', message: `${device.hostname} (${device.ip_address}) is unreachable` });
          }
          const cpu = r.metrics && r.metrics.cpu_utilization;
          if (cpu != null && cpu >= CPU_THRESHOLD) {
            await raiseAlert({ device_id: device.id, severity: 'warning', type: 'high_cpu', message: `${device.hostname} CPU ${cpu}% >= ${CPU_THRESHOLD}%` });
          }
          await device.update({ status: online ? 'online' : 'offline', last_seen: online ? new Date() : device.last_seen });
        } catch (e) { logger.warn({ err: e.message, ip: r.ip_address }, 'monitor persist failed'); }
      }
      await redis.cacheDelPrefix('devices:');
      redis.publish('events', { type: 'monitoring', data: { ts: new Date().toISOString(), checked: devices.length } });
      logger.info('Monitoring cycle complete.');
    });
  }

  async runDiscovery() {
    await redis.withLock('lock:discovery', 30 * 60 * 1000, async () => {
      const network = process.env.DISCOVERY_NETWORK || '192.168.1.0/24';
      try {
        const found = await discoverNetwork(network, { saveToDatabase: true, snmpCommunities: ['public', 'private'], timeout: 2000 });
        logger.info(`Discovery found ${found.length} devices on ${network}`);
        await redis.cacheDelPrefix('devices:');
      } catch (e) { logger.error({ err: e.message }, 'discovery failed'); }
    });
  }

  async start() {
    if (this.isRunning) return;
    this.isRunning = true;
    logger.info('Starting worker service...');
    await redis.connect();
    await this.waitForSchema();
    this.timers.push(setInterval(() => this.runDiscovery().catch((e) => logger.error(e.message)), 6 * 60 * 60 * 1000));
    this.timers.push(setInterval(() => this.runMonitoring().catch((e) => logger.error(e.message)), 5 * 60 * 1000));
    await this.runDiscovery().catch((e) => logger.error(e.message));
    await this.runMonitoring().catch((e) => logger.error(e.message));
  }

  async stop() { this.isRunning = false; this.timers.forEach(clearInterval); this.timers = []; logger.info('Worker stopped'); }
}

if (require.main === module) {
  const worker = new WorkerService();
  worker.start().catch((e) => { logger.error({ err: e.message }, 'worker failed to start'); process.exit(1); });
  process.on('SIGINT', async () => { await worker.stop(); process.exit(0); });
  process.on('SIGTERM', async () => { await worker.stop(); process.exit(0); });
}

module.exports = WorkerService;
