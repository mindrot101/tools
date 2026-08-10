const snmp = require('net-snmp');
const { decrypt } = require('../utils/crypto');

class SNMPManager {
  static createSession(device) {
    const version = String(device.snmp_version || '2c');
    const opts = { port: device.snmp_port || 161, retries: 1, timeout: 3000 };
    if (version === '3') {
      const user = {
        name: device.snmp_user || 'admin',
        level: snmp.SecurityLevel[device.snmp_security_level || 'authPriv'],
        authProtocol: snmp.AuthProtocols[device.snmp_auth_protocol || 'sha'],
        authKey: decrypt(device.snmp_auth_key) || '',
        privProtocol: snmp.PrivProtocols[device.snmp_priv_protocol || 'aes'],
        privKey: decrypt(device.snmp_priv_key) || ''
      };
      return snmp.createV3Session(device.ip_address, user, opts);
    }
    const v = version === '1' ? snmp.Version1 : snmp.Version2c;
    return snmp.createSession(device.ip_address, device.snmp_community || 'public', { ...opts, version: v });
  }

  static _val(v) { return Buffer.isBuffer(v) ? v.toString() : v; }

  static get(device, oids) {
    const list = Array.isArray(oids) ? oids : [oids];
    return new Promise((resolve, reject) => {
      const session = this.createSession(device);
      session.get(list, (error, varbinds) => {
        session.close();
        if (error) return reject(error);
        const out = {};
        (varbinds || []).forEach((vb) => { if (!snmp.isVarbindError(vb)) out[vb.oid] = SNMPManager._val(vb.value); });
        resolve(out);
      });
    });
  }

  static walk(device, oid) {
    return new Promise((resolve, reject) => {
      const session = this.createSession(device);
      const results = [];
      session.subtree(oid, 20,
        (varbinds) => varbinds.forEach((vb) => { if (!snmp.isVarbindError(vb)) results.push({ oid: vb.oid, value: SNMPManager._val(vb.value) }); }),
        (error) => { session.close(); if (error) reject(error); else resolve(results); });
    });
  }

  static getSystemDescription(device) {
    return this.get(device, '1.3.6.1.2.1.1.1.0').then((r) => r['1.3.6.1.2.1.1.1.0'] || 'Unknown');
  }

  static getInterfaces(device) {
    return this.walk(device, '1.3.6.1.2.1.2.2').then((vbs) => {
      const ifs = {};
      vbs.forEach((vb) => {
        const parts = vb.oid.split('.');
        const index = parts.pop();
        const field = parts.join('.');
        if (!ifs[index]) ifs[index] = { index };
        ifs[index][field] = vb.value;
      });
      return Object.values(ifs);
    });
  }

  static getCPUUtilization(device) {
    const oids = ['1.3.6.1.4.1.9.2.1.58.0', '1.3.6.1.4.1.2636.3.1.13.1.8.0', '1.3.6.1.2.1.25.3.3.1.2.1'];
    return this.get(device, oids).then((r) => {
      for (const k of Object.keys(r)) { if (r[k] != null) return parseFloat(r[k]); }
      return null;
    }).catch(() => null);
  }

  static getMemoryUtilization(device) {
    const oids = ['1.3.6.1.2.1.25.2.2.0', '1.3.6.1.2.1.25.2.3.1.6.1'];
    return this.get(device, oids).then((r) => {
      const total = (r['1.3.6.1.2.1.25.2.2.0'] || 0) * 1024;
      const used = (r['1.3.6.1.2.1.25.2.3.1.6.1'] || 0) * 1024;
      return { total, used, free: total - used, usagePercent: total ? (used / total) * 100 : 0 };
    }).catch(() => ({ total: 0, used: 0, free: 0, usagePercent: 0 }));
  }
}

module.exports = { SNMPManager };
