const Telnet = require('telnet-client');
const { decrypt } = require('../utils/crypto');

/**
 * Telnet Connection Manager
 * Handles Telnet connections to network devices
 */
class TelnetManager {
  /**
   * Establish Telnet connection to a device
   * @param {Object} device - Device object with connection details
   * @param {Object} options - Connection options
   * @returns {Promise<Object>} Telnet connection instance
   */
  static connect(device, options = {}) {
    return new Promise((resolve, reject) => {
      const connection = new Telnet();
      
      const params = {
        host: device.ip_address,
        port: device.telnet_port || 23,
        username: device.username,
        password: decrypt(device.password_encrypted),
        timeout: options.timeout || 10000,
        ...options
      };
      
      connection.connect(params)
        .then(() => {
          console.log(`Telnet connection established to ${device.ip_address}`);
          resolve(connection);
        })
        .catch(err => {
          console.error(`Telnet connection error to ${device.ip_address}:`, err);
          reject(err);
        });
    });
  }
  
  /**
   * Execute command over Telnet
   * @param {Object} conn - Telnet connection
   * @param {string} command - Command to execute
   * @param {Object} options - Execution options
   * @returns {Promise<string>} Command output
   */
  static exec(conn, command, options = {}) {
    return new Promise((resolve, reject) => {
      const {
        echoLines = 0, // Number of lines to echo back (command itself)
        waitFor = '' // String to wait for before resolving
      } = options;
      
      conn.exec(command, {
        echoLines,
        waitFor
      })
      .then(output => {
        resolve(output.trim());
      })
      .catch(err => {
        reject(err);
      });
    });
  }
  
  /**
   * Disconnect Telnet connection
   * @param {Object} conn - Telnet connection
   */
  static disconnect(conn) {
    if (conn) {
      conn.end();
    }
  }
  
  /**
   * Send interrupt sequence (Ctrl+C)
   * @param {Object} conn - Telnet connection
   * @returns {Promise<void>}
   */
  static interrupt(conn) {
    return new Promise((resolve, reject) => {
      conn.interrupt()
        .then(() => resolve())
        .catch(err => reject(err));
    });
  }
}

module.exports = { TelnetManager };