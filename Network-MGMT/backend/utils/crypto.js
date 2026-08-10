const crypto = require('crypto');
const ALGO = 'aes-256-gcm';

function getKey() {
  const secret = process.env.ENCRYPTION_KEY || 'dev-insecure-key-change-me';
  return crypto.createHash('sha256').update(secret).digest(); // 32 bytes
}

// Returns "iv:tag:ciphertext" (all base64)
function encrypt(plain) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv(ALGO, getKey(), iv);
  const enc = Buffer.concat([cipher.update(String(plain ?? ''), 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return `${iv.toString('base64')}:${tag.toString('base64')}:${enc.toString('base64')}`;
}

function decrypt(payload) {
  try {
    if (!payload || typeof payload !== 'string' || payload.split(':').length !== 3) return '';
    const [ivB, tagB, dataB] = payload.split(':');
    const decipher = crypto.createDecipheriv(ALGO, getKey(), Buffer.from(ivB, 'base64'));
    decipher.setAuthTag(Buffer.from(tagB, 'base64'));
    const dec = Buffer.concat([decipher.update(Buffer.from(dataB, 'base64')), decipher.final()]);
    return dec.toString('utf8');
  } catch (e) {
    return '';
  }
}

module.exports = { encrypt, decrypt };
