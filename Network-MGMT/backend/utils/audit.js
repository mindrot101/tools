const { AuditLog } = require('../models');
const logger = require('./logger');

async function audit(req, action, target, detail) {
  try {
    await AuditLog.create({
      user_id: req.user && req.user.id,
      username: req.user && req.user.username,
      action,
      target: target || null,
      detail: detail != null ? String(detail).slice(0, 2000) : null,
      ip_address: req.ip
    });
  } catch (e) {
    logger.warn({ err: e.message }, 'audit write failed');
  }
}

module.exports = { audit };
