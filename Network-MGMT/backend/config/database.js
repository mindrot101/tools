const { Sequelize } = require('sequelize');
require('dotenv').config();

const commonOptions = {
  dialect: 'postgres',
  logging: false,
  pool: { max: 5, min: 0, acquire: 30000, idle: 10000 }
};

let sequelize;
if (process.env.DATABASE_URL) {
  // docker-compose supplies DATABASE_URL=postgresql://user:pass@postgres:5432/db
  sequelize = new Sequelize(process.env.DATABASE_URL, commonOptions);
} else {
  sequelize = new Sequelize(
    process.env.POSTGRES_DB || 'network_mgmt',
    process.env.POSTGRES_USER || 'network_user',
    process.env.POSTGRES_PASSWORD || 'network_pass',
    {
      host: process.env.POSTGRES_HOST || 'localhost',
      port: process.env.POSTGRES_PORT || 5432,
      ...commonOptions
    }
  );
}

// Convenience helper (optional)
sequelize.testConnection = async () => {
  await sequelize.authenticate();
};

module.exports = sequelize;
