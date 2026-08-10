const Client = require('ssh2').Client;
const { decrypt } = require('../utils/crypto');

/**
 * SSH Connection Manager
 * Handles SSH connections to network devices
 */
class SSHManager {
  /**
   * Establish SSH connection to a device
   * @param {Object} device - Device object with connection details
   * @param {Object} options - Connection options
   * @returns {Promise<Client>} SSH client instance
   */
  static connect(device, options = {}) {
    return new Promise((resolve, reject) => {
      const conn = new Client();
      
      conn.on('ready', () => {
        console.log(`SSH connection established to ${device.ip_address}`);
        resolve(conn);
      });
      
      conn.on('error', (err) => {
        console.error(`SSH connection error to ${device.ip_address}:`, err);
        reject(err);
      });
      
      conn.on('close', () => {
        console.log(`SSH connection closed to ${device.ip_address}`);
      });
      
      conn.on('end', () => {
        console.log(`SSH connection ended to ${device.ip_address}`);
      });
      
      // Connection configuration
      const config = {
        host: device.ip_address,
        port: device.ssh_port || 22,
        username: device.username,
        password: decrypt(device.password_encrypted),
        readyTimeout: options.timeout || 10000,
        ...options
      };
      
      conn.connect(config);
    });
  }
  
  /**
   * Execute command over SSH
   * @param {Client} conn - SSH connection
   * @param {string} command - Command to execute
   * @returns {Promise<string>} Command output
   */
  static exec(conn, command) {
    return new Promise((resolve, reject) => {
      conn.exec(command, (err, stream) => {
        if (err) {
          reject(err);
          return;
        }
        
        let output = '';
        let errorOutput = '';
        
        stream.on('close', (code, signal) => {
          if (code !== 0) {
            reject(new Error(`Command failed with exit code ${code}: ${errorOutput}`));
          } else {
            resolve(output.trim());
          }
        });
        
        stream.on('data', (data) => {
          output += data.toString();
        });
        
        stream.stderr.on('data', (data) => {
          errorOutput += data.toString();
        });
        
        stream.end();
      });
    });
  }
  
  /**
   * Disconnect SSH connection
   * @param {Client} conn - SSH connection
   */
  static disconnect(conn) {
    if (conn) {
      conn.end();
    }
  }
}

SSHManager.executeCommand = SSHManager.exec;
module.exports = { SSHManager };