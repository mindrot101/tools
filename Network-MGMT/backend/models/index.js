const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');

const Device = sequelize.define('Device', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  hostname: { type: DataTypes.STRING, allowNull: false, unique: true },
  ip_address: { type: DataTypes.STRING, allowNull: false },
  vendor: { type: DataTypes.ENUM('cisco', 'palo_alto', 'aruba', 'arista', 'juniper', 'other'), allowNull: false },
  device_type: { type: DataTypes.ENUM('router', 'switch', 'firewall', 'load_balancer', 'other'), allowNull: false },
  username: { type: DataTypes.STRING, allowNull: false },
  password_encrypted: { type: DataTypes.STRING(1024), allowNull: false },
  enable_password: { type: DataTypes.STRING(1024), allowNull: true },
  ssh_port: { type: DataTypes.INTEGER, defaultValue: 22 },
  telnet_port: { type: DataTypes.INTEGER, defaultValue: 23 },
  snmp_port: { type: DataTypes.INTEGER, defaultValue: 161 },
  snmp_version: { type: DataTypes.STRING, defaultValue: '2c' },
  snmp_community: { type: DataTypes.STRING, defaultValue: 'public' },
  snmp_user: { type: DataTypes.STRING, allowNull: true },
  snmp_security_level: { type: DataTypes.STRING, defaultValue: 'authPriv' },
  snmp_auth_protocol: { type: DataTypes.STRING, defaultValue: 'sha' },
  snmp_auth_key: { type: DataTypes.STRING(1024), allowNull: true },
  snmp_priv_protocol: { type: DataTypes.STRING, defaultValue: 'aes' },
  snmp_priv_key: { type: DataTypes.STRING(1024), allowNull: true },
  status: { type: DataTypes.ENUM('online', 'offline', 'unknown', 'maintenance'), defaultValue: 'unknown' },
  last_seen: { type: DataTypes.DATE, allowNull: true },
  notes: { type: DataTypes.TEXT, allowNull: true }
}, {
  timestamps: true,
  tableName: 'devices',
  indexes: [
    { fields: ['status'] },
    { fields: ['vendor'] },
    { fields: ['ip_address'] }
  ]
});

const User = sequelize.define('User', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  username: { type: DataTypes.STRING, allowNull: false, unique: true },
  email: { type: DataTypes.STRING, allowNull: false, unique: true },
  password_hash: { type: DataTypes.STRING, allowNull: false },
  role: { type: DataTypes.ENUM('admin', 'operator', 'viewer'), defaultValue: 'viewer' },
  is_active: { type: DataTypes.BOOLEAN, defaultValue: true }
}, { timestamps: true, tableName: 'users' });

const Session = sequelize.define('Session', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  user_id: { type: DataTypes.UUID, allowNull: false, references: { model: User, key: 'id' } },
  token: { type: DataTypes.STRING, allowNull: false, unique: true },
  expires_at: { type: DataTypes.DATE, allowNull: false },
  ip_address: { type: DataTypes.STRING, allowNull: true },
  user_agent: { type: DataTypes.STRING, allowNull: true }
}, { timestamps: true, tableName: 'sessions' });

const MonitoringResult = sequelize.define('MonitoringResult', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  device_id: { type: DataTypes.UUID, allowNull: false, references: { model: Device, key: 'id' } },
  ping: { type: DataTypes.BOOLEAN, defaultValue: false },
  ssh: { type: DataTypes.BOOLEAN, defaultValue: false },
  telnet: { type: DataTypes.BOOLEAN, defaultValue: false },
  snmp: { type: DataTypes.BOOLEAN, defaultValue: false },
  response_time_ms: { type: DataTypes.INTEGER, allowNull: true },
  error: { type: DataTypes.TEXT, allowNull: true },
  cpu_utilization: { type: DataTypes.FLOAT, allowNull: true },
  memory_utilization: { type: DataTypes.FLOAT, allowNull: true }
}, { timestamps: true, tableName: 'monitoring_results', indexes: [{ fields: ['device_id'] }, { fields: ['createdAt'] }] });

const ConfigBackup = sequelize.define('ConfigBackup', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  device_id: { type: DataTypes.UUID, allowNull: false, references: { model: Device, key: 'id' } },
  config: { type: DataTypes.TEXT, allowNull: false },
  hash: { type: DataTypes.STRING, allowNull: true },
  changed_by: { type: DataTypes.UUID, allowNull: true, references: { model: User, key: 'id' } }
}, { timestamps: true, tableName: 'config_backups', indexes: [{ fields: ['device_id'] }] });

const Alert = sequelize.define('Alert', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  device_id: { type: DataTypes.UUID, allowNull: true, references: { model: Device, key: 'id' } },
  severity: { type: DataTypes.ENUM('info', 'warning', 'critical'), defaultValue: 'warning' },
  type: { type: DataTypes.STRING, allowNull: false },
  message: { type: DataTypes.TEXT, allowNull: false },
  acknowledged: { type: DataTypes.BOOLEAN, defaultValue: false }
}, { timestamps: true, tableName: 'alerts', indexes: [{ fields: ['device_id'] }, { fields: ['acknowledged'] }] });

const AuditLog = sequelize.define('AuditLog', {
  id: { type: DataTypes.UUID, defaultValue: DataTypes.UUIDV4, primaryKey: true },
  user_id: { type: DataTypes.UUID, allowNull: true },
  username: { type: DataTypes.STRING, allowNull: true },
  action: { type: DataTypes.STRING, allowNull: false },
  target: { type: DataTypes.STRING, allowNull: true },
  detail: { type: DataTypes.TEXT, allowNull: true },
  ip_address: { type: DataTypes.STRING, allowNull: true }
}, { timestamps: true, tableName: 'audit_logs', indexes: [{ fields: ['user_id'] }, { fields: ['action'] }] });

// Associations
Device.hasMany(MonitoringResult, { foreignKey: 'device_id', onDelete: 'CASCADE' });
MonitoringResult.belongsTo(Device, { foreignKey: 'device_id' });
Device.hasMany(ConfigBackup, { foreignKey: 'device_id', onDelete: 'CASCADE' });
ConfigBackup.belongsTo(Device, { foreignKey: 'device_id' });
Device.hasMany(Alert, { foreignKey: 'device_id', onDelete: 'CASCADE' });
Alert.belongsTo(Device, { foreignKey: 'device_id' });
User.hasMany(Session, { foreignKey: 'user_id', onDelete: 'CASCADE' });
Session.belongsTo(User, { foreignKey: 'user_id' });

module.exports = { sequelize, Device, User, Session, MonitoringResult, ConfigBackup, Alert, AuditLog };
