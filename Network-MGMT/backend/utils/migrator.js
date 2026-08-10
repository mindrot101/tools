const path = require('path');
const { Umzug, SequelizeStorage } = require('umzug');
const sequelize = require('../config/database');
const logger = require('./logger');

function buildMigrator() {
  return new Umzug({
    migrations: { glob: path.join(__dirname, '..', 'migrations', '*.js') },
    context: sequelize.getQueryInterface(),
    storage: new SequelizeStorage({ sequelize }),
    logger: { info: (m) => logger.info(m), warn: (m) => logger.warn(m), error: (m) => logger.error(m), debug: () => {} }
  });
}

async function runMigrations() {
  const umzug = buildMigrator();
  const pending = await umzug.pending();
  if (pending.length) { logger.info(`Running ${pending.length} pending migration(s)`); await umzug.up(); }
  return pending.length;
}

module.exports = { buildMigrator, runMigrations };
