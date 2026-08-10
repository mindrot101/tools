import { useState, useEffect } from 'react';
import { Box, Typography, Card, CardContent, Grid, Divider, Stack, Alert, Chip } from '@mui/material';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { getSocket } from '../services/socket';

const Stat = ({ label, value, color, onClick }) => (
  <Card sx={{ cursor: onClick ? 'pointer' : 'default' }} onClick={onClick}>
    <CardContent><Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="h3" color={color}>{value}</Typography></CardContent>
  </Card>
);

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState({ total: 0, online: 0, offline: 0, unknown: 0 });
  const [alerts, setAlerts] = useState(0);
  const [live, setLive] = useState(false);
  const [error, setError] = useState('');

  const load = () => {
    api.get('/devices/stats').then((r) => setStats(r.data)).catch(() => setError('Failed to load stats'));
    api.get('/alerts', { params: { acknowledged: 'false', limit: 500 } }).then((r) => setAlerts(r.data.length)).catch(() => {});
  };

  useEffect(() => {
    load();
    const s = getSocket();
    const onConn = () => setLive(true);
    const onEvt = () => load();
    s.on('connect', onConn); s.on('alert', onEvt); s.on('monitoring', onEvt);
    if (s.connected) setLive(true);
    return () => { s.off('connect', onConn); s.off('alert', onEvt); s.off('monitoring', onEvt); };
  }, []);

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1 }}>
        <Typography variant="h4">Network Management Dashboard</Typography>
        <Chip size="small" color={live ? 'success' : 'default'} label={live ? 'live' : 'offline'} />
      </Stack>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>Welcome back, {user?.username || 'Administrator'}!</Typography>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Grid container spacing={3}>
        <Grid item xs={6} md={3}><Stat label="Total Devices" value={stats.total} onClick={() => navigate('/devices')} /></Grid>
        <Grid item xs={6} md={3}><Stat label="Online" value={stats.online} color="success.main" onClick={() => navigate('/monitoring')} /></Grid>
        <Grid item xs={6} md={3}><Stat label="Offline" value={stats.offline} color="error.main" onClick={() => navigate('/devices')} /></Grid>
        <Grid item xs={6} md={3}><Stat label="Open Alerts" value={alerts} color="warning.main" onClick={() => navigate('/alerts')} /></Grid>
      </Grid>
      <Divider sx={{ my: 4 }} />
      <Typography variant="h5" gutterBottom>Quick Actions</Typography>
      <Grid container spacing={2}>
        {[{ t: 'Add / manage devices', p: '/devices' }, { t: 'Run health checks', p: '/monitoring' }, { t: 'Discover the network', p: '/discovery' }].map((a) => (
          <Grid item xs={12} sm={4} key={a.p}>
            <Card sx={{ cursor: 'pointer' }} onClick={() => navigate(a.p)}><CardContent><Typography variant="h6">{a.t}</Typography></CardContent></Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
