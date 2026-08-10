const { Alert } = require('../models');
const logger = require('./logger');
const redis = require('./redis');
const { sendMail } = require('./email');

async function raiseAlert({ device_id = null, severity = 'warning', type, message }) {
  try {
    const alert = await Alert.create({ device_id, severity, type, message });
    const payload = { severity, type, message, device_id, id: alert.id, ts: new Date().toISOString() };
    // live push (worker publishes; backend socket bridge re-emits)
    redis.publish('events', { type: 'alert', data: payload });
    // optional webhook
    const url = process.env.ALERT_WEBHOOK_URL;
    if (url && typeof fetch === 'function') {
      fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        .catch((e) => logger.warn({ err: e.message }, 'alert webhook failed'));
    }
    // optional email
    if (severity === 'critical' || severity === 'warning') {
      sendMail(`[NetMgmt ${severity}] ${type}`, message);
    }
    return alert;
  } catch (e) {
    logger.warn({ err: e.message }, 'raiseAlert failed');
  }
}

module.exports = { raiseAlert };
