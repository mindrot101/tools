const http = require('http');
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const pinoHttp = require('pino-http');
const rateLimit = require('express-rate-limit');
const bcrypt = require('bcryptjs');
const swaggerUi = require('swagger-ui-express');
const sequelize = require('./config/database');
const { User } = require('./models');
const logger = require('./utils/logger');
const redis = require('./utils/redis');
const { getSecret } = require('./middleware/auth');
const { initSocket } = require('./utils/socket');
const { runMigrations } = require('./utils/migrator');
const openapi = require('./openapi.json');

const authRoutes = require('./routes/auth');
const deviceRoutes = require('./routes/devices');
const alertRoutes = require('./routes/alerts');
const auditRoutes = require('./routes/audit');

const app = express();
app.set('trust proxy', 1);

const origins = (process.env.CORS_ORIGIN || '').split(',').map((s) => s.trim()).filter(Boolean);
app.use(cors({ origin: origins.length ? (origins.includes('*') ? true : origins) : true, credentials: true }));
app.use(helmet());
app.use(pinoHttp({ logger, autoLogging: { ignore: (req) => req.url === '/health' } }));
app.use(express.json({ limit: '1mb' }));
app.use(express.urlencoded({ extended: true }));
app.use(rateLimit({ windowMs: 60 * 1000, max: 300, standardHeaders: true, legacyHeaders: false }));

app.get('/health', (req, res) => res.json({ status: 'healthy', timestamp: new Date().toISOString(), uptime: process.uptime() }));
app.use('/api/docs', swaggerUi.serve, swaggerUi.setup(openapi));
app.get('/api/openapi.json', (req, res) => res.json(openapi));

app.use('/api/auth', authRoutes);
app.use('/api/devices', deviceRoutes);
app.use('/api/alerts', alertRoutes);
app.use('/api/audit', auditRoutes);

app.use((req, res) => res.status(404).json({ msg: 'Route not found' }));
app.use((err, req, res, next) => {
  logger.error({ err: err.message }, 'unhandled error');
  res.status(500).json({ msg: 'Internal server error', error: process.env.NODE_ENV === 'development' ? err.message : undefined });
});

async function seedAdmin() {
  const [, created] = await User.findOrCreate({
    where: { username: 'admin' },
    defaults: { email: 'admin@example.com', password_hash: bcrypt.hashSync('admin', 10), role: 'admin', is_active: true }
  });
  if (created) logger.warn('Seeded default admin (admin/admin) - change this password immediately.');
}

const PORT = process.env.PORT || 3000;
const server = http.createServer(app);

sequelize.authenticate()
  .then(() => { logger.info('Database connected'); return sequelize.sync({ alter: process.env.DB_SYNC_ALTER === 'true' }); })
  .then(async () => {
    logger.info('Database synchronized');
    try { getSecret(); } catch (e) { logger.error(e.message); process.exit(1); }
    await runMigrations();
    await seedAdmin();
    await redis.connect();
    initSocket(server);
    server.listen(PORT, () => logger.info(`Server running on port ${PORT} (env: ${process.env.NODE_ENV || 'development'})`));
  })
  .catch((err) => { logger.error({ err: err.message }, 'startup failed'); process.exit(1); });

module.exports = app;
