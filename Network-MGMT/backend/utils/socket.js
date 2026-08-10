const { Server } = require('socket.io');
const jwt = require('jsonwebtoken');
const { getSecret } = require('../middleware/auth');
const redis = require('./redis');
const logger = require('./logger');

let io = null;

function initSocket(httpServer) {
  io = new Server(httpServer, { path: '/socket.io', cors: { origin: true } });
  io.use((socket, next) => {
    const token = socket.handshake.auth && socket.handshake.auth.token;
    if (token) { try { socket.user = jwt.verify(token, getSecret()).user; } catch {} }
    next();
  });
  io.on('connection', () => logger.debug('socket client connected'));
  // Bridge events published by the worker (separate process) to connected clients
  redis.subscribe('events', (evt) => { if (io && evt && evt.type) io.emit(evt.type, evt.data); });
  logger.info('socket.io initialized');
  return io;
}

function emit(type, data) { if (io) io.emit(type, data); }

module.exports = { initSocket, emit };
