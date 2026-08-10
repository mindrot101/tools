const express = require('express');
const router = express.Router();
const crypto = require('crypto');
const { Op } = require('sequelize');
const { body, validationResult } = require('express-validator');
const { Device, MonitoringResult, ConfigBackup } = require('../models');
const { auth, requireRole } = require('../middleware/auth');
const { encrypt } = require('../utils/crypto');
const { discoverNetwork } = require('../services/discovery');
const { monitorDevices, healthCheck } = require('../services/monitoring');
const { SSHManager } = require('../protocols/ssh');
const { audit } = require('../utils/audit');
const { cacheGet, cacheSet, cacheDelPrefix } = require('../utils/redis');
const { emit } = require('../utils/socket');
const logger = require('../utils/logger');

const writer = requireRole('admin', 'operator');
const validate = (req, res, next) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) return res.status(400).json({ msg: 'Validation failed', errors: errors.array() });
  next();
};
const invalidate = () => cacheDelPrefix('devices:');
const publicFields = { attributes: { exclude: ['password_encrypted', 'enable_password', 'snmp_auth_key', 'snmp_priv_key'] } };

// Stats (cached)
router.get('/stats', auth, async (req, res) => {
  try {
    const cached = await cacheGet('devices:stats');
    if (cached) return res.json(cached);
    const rows = await Device.findAll({ attributes: ['status'] });
    const stats = { total: rows.length, online: 0, offline: 0, unknown: 0, maintenance: 0 };
    rows.forEach((r) => { stats[r.status] = (stats[r.status] || 0) + 1; });
    await cacheSet('devices:stats', stats, 15);
    res.json(stats);
  } catch (e) {
    res.status(500).json({ msg: 'Server error' });
  }
});

// List with SQL-side filtering + pagination
router.get('/', auth, async (req, res) => {
  try {
    const { status, vendor, device_type, search } = req.query;
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const limit = Math.min(200, Math.max(1, parseInt(req.query.limit) || 50));
    const where = {};
    if (status) where.status = status;
    if (vendor) where.vendor = vendor;
    if (device_type) where.device_type = device_type;
    if (search) {
      where[Op.or] = [
        { hostname: { [Op.iLike]: `%${search}%` } },
        { ip_address: { [Op.iLike]: `%${search}%` } },
        { notes: { [Op.iLike]: `%${search}%` } }
      ];
    }
    const { rows, count } = await Device.findAndCountAll({
      where, ...publicFields, order: [['hostname', 'ASC']], limit, offset: (page - 1) * limit
    });
    res.json({ data: rows, total: count, page, limit, pages: Math.ceil(count / limit) });
  } catch (e) {
    logger.error({ err: e.message }, 'list devices failed');
    res.status(500).json({ msg: 'Server error' });
  }
});

router.get('/:id', auth, async (req, res) => {
  try {
    const device = await Device.findByPk(req.params.id, publicFields);
    if (!device) return res.status(404).json({ msg: 'Device not found' });
    res.json(device);
  } catch { res.status(500).json({ msg: 'Server error' }); }
});

router.post('/', auth, writer,
  body('hostname').isString().trim().notEmpty(),
  body('ip_address').isString().trim().notEmpty(),
  body('vendor').isIn(['cisco', 'palo_alto', 'aruba', 'arista', 'juniper', 'other']),
  body('device_type').isIn(['router', 'switch', 'firewall', 'load_balancer', 'other']),
  body('username').isString().trim().notEmpty(),
  validate,
  async (req, res) => {
    try {
      const b = req.body;
      const device = await Device.create({
        hostname: b.hostname, ip_address: b.ip_address, vendor: b.vendor, device_type: b.device_type,
        username: b.username, password_encrypted: encrypt(b.password || ''),
        enable_password: b.enable_password ? encrypt(b.enable_password) : null,
        ssh_port: b.ssh_port || 22, telnet_port: b.telnet_port || 23, snmp_port: b.snmp_port || 161,
        snmp_version: b.snmp_version || '2c', snmp_community: b.snmp_community || 'public',
        snmp_user: b.snmp_user || null, snmp_security_level: b.snmp_security_level || 'authPriv',
        snmp_auth_protocol: b.snmp_auth_protocol || 'sha', snmp_auth_key: b.snmp_auth_key ? encrypt(b.snmp_auth_key) : null,
        snmp_priv_protocol: b.snmp_priv_protocol || 'aes', snmp_priv_key: b.snmp_priv_key ? encrypt(b.snmp_priv_key) : null,
        notes: b.notes, status: 'unknown'
      });
      await invalidate();
      await audit(req, 'device.create', device.hostname);
      const { password_encrypted, enable_password, snmp_auth_key, snmp_priv_key, ...safe } = device.toJSON();
      res.status(201).json(safe);
    } catch (e) {
      if (e.name === 'SequelizeUniqueConstraintError') return res.status(409).json({ msg: 'Hostname already exists' });
      res.status(500).json({ msg: 'Server error' });
    }
  }
);

router.put('/:id', auth, writer, async (req, res) => {
  try {
    const device = await Device.findByPk(req.params.id);
    if (!device) return res.status(404).json({ msg: 'Device not found' });
    const b = req.body;
    const upd = {};
    ['hostname', 'ip_address', 'vendor', 'device_type', 'username', 'snmp_version', 'snmp_community', 'notes', 'status'].forEach((k) => {
      if (b[k] !== undefined) upd[k] = b[k];
    });
    ['ssh_port', 'telnet_port', 'snmp_port'].forEach((k) => { if (b[k] !== undefined) upd[k] = b[k]; });
    ['snmp_user', 'snmp_security_level', 'snmp_auth_protocol', 'snmp_priv_protocol'].forEach((k) => { if (b[k] !== undefined) upd[k] = b[k]; });
    if (b.snmp_auth_key !== undefined) upd.snmp_auth_key = b.snmp_auth_key ? encrypt(b.snmp_auth_key) : null;
    if (b.snmp_priv_key !== undefined) upd.snmp_priv_key = b.snmp_priv_key ? encrypt(b.snmp_priv_key) : null;
    if (b.password !== undefined) upd.password_encrypted = encrypt(b.password);
    if (b.enable_password !== undefined) upd.enable_password = b.enable_password ? encrypt(b.enable_password) : null;
    await device.update(upd);
    await invalidate();
    await audit(req, 'device.update', device.hostname);
    const { password_encrypted, enable_password, snmp_auth_key, snmp_priv_key, ...safe } = device.toJSON();
    res.json(safe);
  } catch { res.status(500).json({ msg: 'Server error' }); }
});

router.delete('/:id', auth, requireRole('admin'), async (req, res) => {
  try {
    const device = await Device.findByPk(req.params.id);
    if (!device) return res.status(404).json({ msg: 'Device not found' });
    await device.destroy();
    await invalidate();
    await audit(req, 'device.delete', device.hostname);
    res.json({ msg: 'Device removed successfully' });
  } catch { res.status(500).json({ msg: 'Server error' }); }
});

// Immediate health check (persisted)
router.post('/:id/health-check', auth, writer, async (req, res) => {
  try {
    const device = await Device.findByPk(req.params.id);
    if (!device) return res.status(404).json({ msg: 'Device not found' });
    const result = await healthCheck(device);
    await MonitoringResult.create({
      device_id: device.id, ping: result.ping, ssh: result.ssh, telnet: result.telnet, snmp: result.snmp,
      response_time_ms: result.response_time_ms, error: result.error,
      cpu_utilization: result.metrics && result.metrics.cpu_utilization,
      memory_utilization: result.metrics && result.metrics.memory_utilization
    });
    const isOnline = result.ping || result.ssh || result.telnet || result.snmp;
    await device.update({ status: isOnline ? 'online' : 'offline', last_seen: new Date() });
    await invalidate();
    emit('monitoring', { device_id: device.id, hostname: device.hostname, status: isOnline ? 'online' : 'offline', ts: new Date().toISOString() });
    res.json(result);
  } catch (e) {
    logger.error({ err: e.message }, 'health-check failed');
    res.status(500).json({ msg: 'Server error' });
  }
});

// Monitoring history
router.get('/:id/monitoring', auth, async (req, res) => {
  try {
    const limit = Math.min(500, Math.max(1, parseInt(req.query.limit) || 50));
    const results = await MonitoringResult.findAll({
      where: { device_id: req.params.id }, order: [['createdAt', 'DESC']], limit
    });
    res.json(results);
  } catch { res.status(500).json({ msg: 'Server error' }); }
});

// Network discovery (admin)
router.post('/discover', auth, requireRole('admin'),
  body('network').isString().trim().notEmpty(),
  validate,
  async (req, res) => {
    try {
      const { network, snmp_communities, timeout } = req.body;
      const devices = await discoverNetwork(network, {
        snmpCommunities: snmp_communities || ['public', 'private'], timeout: timeout || 2000, saveToDatabase: true
      });
      await invalidate();
      await audit(req, 'network.discover', network, `found=${devices.length}`);
      res.json({ msg: 'Discovery completed', devices_found: devices.length, devices });
    } catch (e) {
      logger.error({ err: e.message }, 'discovery failed');
      res.status(500).json({ msg: 'Server error' });
    }
  }
);

// Execute command via SSH (admin, audited)
router.post('/:id/execute-command', auth, requireRole('admin'),
  body('command').isString().trim().notEmpty(), validate,
  async (req, res) => {
    let conn;
    try {
      const device = await Device.findByPk(req.params.id);
      if (!device) return res.status(404).json({ msg: 'Device not found' });
      const { command, timeout = 30000 } = req.body;
      conn = await SSHManager.connect(device, { timeout });
      const output = await SSHManager.executeCommand(conn, command);
      await audit(req, 'device.execute', device.hostname, command);
      res.json({ command, output, success: true });
    } catch (e) {
      res.status(500).json({ msg: 'Command execution failed', error: e.message });
    } finally {
      if (conn) SSHManager.disconnect(conn);
    }
  }
);

// Fetch running config and store a versioned backup (admin)
router.get('/:id/config', auth, requireRole('admin'), async (req, res) => {
  let conn;
  try {
    const device = await Device.findByPk(req.params.id);
    if (!device) return res.status(404).json({ msg: 'Device not found' });
    const cmds = {
      cisco: 'show running-config', arista: 'show running-config', aruba: 'show running-config',
      juniper: 'show configuration | display set', palo_alto: 'show config merged'
    };
    conn = await SSHManager.connect(device, { timeout: 30000 });
    const config = await SSHManager.executeCommand(conn, cmds[device.vendor] || 'show running-config');
    const hash = crypto.createHash('sha256').update(config).digest('hex');
    const last = await ConfigBackup.findOne({ where: { device_id: device.id }, order: [['createdAt', 'DESC']] });
    let backup = last;
    if (!last || last.hash !== hash) {
      backup = await ConfigBackup.create({ device_id: device.id, config, hash, changed_by: req.user.id });
    }
    await audit(req, 'device.config_backup', device.hostname, `hash=${hash.slice(0, 12)}`);
    res.json({ device_id: device.id, hostname: device.hostname, config, hash, backup_id: backup && backup.id, timestamp: new Date().toISOString() });
  } catch (e) {
    res.status(500).json({ msg: 'Failed to retrieve configuration', error: e.message });
  } finally {
    if (conn) SSHManager.disconnect(conn);
  }
});

// List config backups
router.get('/:id/backups', auth, async (req, res) => {
  try {
    const backups = await ConfigBackup.findAll({
      where: { device_id: req.params.id }, order: [['createdAt', 'DESC']],
      attributes: ['id', 'hash', 'changed_by', 'createdAt']
    });
    res.json(backups);
  } catch { res.status(500).json({ msg: 'Server error' }); }
});

module.exports = router;
