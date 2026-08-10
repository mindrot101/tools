const nodemailer = require('nodemailer');
const logger = require('./logger');

let transport = null;
if (process.env.SMTP_HOST) {
  transport = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: parseInt(process.env.SMTP_PORT) || 587,
    secure: process.env.SMTP_SECURE === 'true',
    auth: process.env.SMTP_USER ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS } : undefined
  });
  logger.info('SMTP transport configured');
}

async function sendMail(subject, text) {
  if (!transport || !process.env.ALERT_EMAIL_TO) return;
  try {
    await transport.sendMail({ from: process.env.SMTP_FROM || 'netmgmt@localhost', to: process.env.ALERT_EMAIL_TO, subject, text });
  } catch (e) {
    logger.warn({ err: e.message }, 'email send failed');
  }
}

module.exports = { sendMail };
