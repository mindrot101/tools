const ping = require('ping');
const { SNMPManager } = require('../protocols/snmp');
const { Device } = require('../models');
const { mapLimit } = require('../utils/concurrency');
const { encrypt } = require('../utils/crypto');
const logger = require('../utils/logger');

const MAX_HOSTS = parseInt(process.env.DISCOVERY_MAX_HOSTS) || 4096;

function cidrHosts(network) {
  const [base, prefixStr] = String(network).split('/');
  const prefix = parseInt(prefixStr);
  if (isNaN(prefix) || prefix < 0 || prefix > 32) throw new Error(`Invalid CIDR: ${network}`);
  const toInt = (ip) => ip.split('.').reduce((a, o) => ((a << 8) + (parseInt(o) & 255)) >>> 0, 0) >>> 0;
  const toIp = (n) => [24, 16, 8, 0].map((s) => (n >>> s) & 255).join('.');
  const baseInt = toInt(base);
  const mask = prefix === 0 ? 0 : (0xFFFFFFFF << (32 - prefix)) >>> 0;
  const net = (baseInt & mask) >>> 0;
  const bcast = (net | (~mask >>> 0)) >>> 0;
  const hosts = [];
  const start = prefix >= 31 ? net : net + 1;
  const end = prefix >= 31 ? bcast : bcast - 1;
  for (let n = start; n <= end && hosts.length < MAX_HOSTS; n++) hosts.push(toIp(n >>> 0));
  if (end - start + 1 > MAX_HOSTS) logger.warn(`Discovery capped at ${MAX_HOSTS} hosts for ${network}`);
  return hosts;
}

class DiscoveryService {
  static async pingSweep(network, options = {}) {
    const { timeout = 2000, maxConcurrent = 50 } = options;
    const ipList = cidrHosts(network);
    const results = await mapLimit(ipList, maxConcurrent, async (ip) => {
      try {
        const r = await ping.promise.probe(ip, { timeout: Math.ceil(timeout / 1000), min_reply: 1 });
        return r.alive ? ip : null;
      } catch { return null; }
    });
    return results.filter(Boolean);
  }

  static async identifyDeviceViaSNMP(ipAddress, snmpOptions = {}) {
    const dev = {
      ip_address: ipAddress, snmp_port: snmpOptions.port || 161,
      snmp_community: snmpOptions.community || 'public', snmp_version: '2c'
    };
    try {
      const r = await SNMPManager.get(dev, ['1.3.6.1.2.1.1.1.0', '1.3.6.1.2.1.1.5.0']);
      const sysDescr = r['1.3.6.1.2.1.1.1.0'] || '';
      const sysName = r['1.3.6.1.2.1.1.5.0'] || '';
      if (!sysDescr) return { ip_address: ipAddress, hostname: null, vendor: 'other', device_type: 'other', sys_descr: null, snmp_responds: false };
      return {
        ip_address: ipAddress, hostname: sysName || null,
        vendor: this._identifyVendor(sysDescr), device_type: this._identifyDeviceType(sysDescr, sysName),
        sys_descr: sysDescr, snmp_responds: true
      };
    } catch {
      return { ip_address: ipAddress, hostname: null, vendor: 'other', device_type: 'other', sys_descr: null, snmp_responds: false };
    }
  }

  static _identifyVendor(sysDescr) {
    const l = String(sysDescr).toLowerCase();
    if (l.includes('cisco')) return 'cisco';
    if (l.includes('palo alto') || l.includes('panos')) return 'palo_alto';
    if (l.includes('aruba') || l.includes('hp') || l.includes('hewlett')) return 'aruba';
    if (l.includes('arista')) return 'arista';
    if (l.includes('juniper') || l.includes('junos')) return 'juniper';
    return 'other';
  }

  static _identifyDeviceType(sysDescr, sysName) {
    const c = (String(sysDescr) + ' ' + String(sysName)).toLowerCase();
    if (c.includes('router') || c.includes('isr') || c.includes('asr')) return 'router';
    if (c.includes('switch') || c.includes('catalyst') || c.includes('nexus')) return 'switch';
    if (c.includes('firewall') || c.includes('asa') || c.includes('panos') || c.includes('srx')) return 'firewall';
    if (c.includes('load balancer') || c.includes('big-ip')) return 'load_balancer';
    return 'other';
  }

  static async discoverNetwork(network, options = {}) {
    const { snmpCommunities = ['public', 'private'], timeout = 2000, maxConcurrent = 50, saveToDatabase = false } = options;
    logger.info(`Starting network discovery for ${network}...`);
    const responsiveIps = await this.pingSweep(network, { timeout, maxConcurrent });
    logger.info(`Found ${responsiveIps.length} responsive IP addresses`);

    const devices = await mapLimit(responsiveIps, Math.min(maxConcurrent, 20), async (ip) => {
      for (const community of snmpCommunities) {
        const info = await this.identifyDeviceViaSNMP(ip, { community });
        if (info.snmp_responds) return info;
      }
      return { ip_address: ip, hostname: null, vendor: 'other', device_type: 'other', sys_descr: null, snmp_responds: false };
    });

    if (saveToDatabase && devices.length > 0) await this._saveDiscoveredDevices(devices);
    logger.info(`Discovery complete. ${devices.length} devices.`);
    return devices;
  }

  static async _saveDiscoveredDevices(devices) {
    for (const d of devices) {
      try {
        let device = await Device.findOne({ where: { ip_address: d.ip_address } });
        if (!device) {
          await Device.create({
            hostname: d.hostname || `unknown-${d.ip_address.replace(/\./g, '-')}`,
            ip_address: d.ip_address, vendor: d.vendor, device_type: d.device_type,
            username: 'admin', password_encrypted: encrypt(''),
            status: d.snmp_responds ? 'online' : 'unknown', last_seen: new Date(),
            notes: `Discovered via network scan${d.sys_descr ? `: ${d.sys_descr.substring(0, 120)}` : ''}`
          });
        } else {
          await device.update({
            hostname: d.hostname || device.hostname,
            vendor: d.vendor !== 'other' ? d.vendor : device.vendor,
            device_type: d.device_type !== 'other' ? d.device_type : device.device_type,
            status: d.snmp_responds ? 'online' : device.status, last_seen: new Date()
          });
        }
      } catch (e) {
        logger.warn({ err: e.message, ip: d.ip_address }, 'save discovered device failed');
      }
    }
  }
}

module.exports = DiscoveryService;
module.exports.discoverNetwork = DiscoveryService.discoverNetwork.bind(DiscoveryService);
module.exports.pingSweep = DiscoveryService.pingSweep.bind(DiscoveryService);
module.exports.cidrHosts = cidrHosts;
