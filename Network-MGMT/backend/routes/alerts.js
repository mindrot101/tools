const express = require('express');
const router = express.Router();
const { Alert, Device } = require('../models');
const { auth, requireRole } = require('../middleware/auth');

router.get('/', auth, async (req, res) => {
  try {
    const where = {};
    if (req.query.acknowledged === 'false') where.acknowledged = false;
    if (req.query.acknowledged === 'true') where.acknowledged = true;
    const limit = Math.min(500, Math.max(1, parseInt(req.query.limit) || 100));
    const alerts = await Alert.findAll({
      where, order: [['createdAt', 'DESC']], limit,
      include: [{ model: Device, attributes: ['hostname', 'ip_address'] }]
    });
    res.json(alerts);
  } catch { res.status(500).json({ msg: 'Server error' }); }
});

router.post('/:id/ack', auth, requireRole('admin', 'operator'), async (req, res) => {
  try {
    const alert = await Alert.findByPk(req.params.id);
    if (!alert) return res.status(404).json({ msg: 'Alert not found' });
    await alert.update({ acknowledged: true });
    res.json(alert);
  } catch { res.status(500).json({ msg: 'Server error' }); }
});

module.exports = router;
