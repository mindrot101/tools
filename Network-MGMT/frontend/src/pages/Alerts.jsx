import { useState, useEffect } from 'react';
import { Box, Typography, Button, Alert as MuiAlert, CircularProgress, Chip, Stack, Table, TableHead, TableRow, TableCell, TableBody, TableContainer, Paper } from '@mui/material';
import api from '../services/api';
import { getSocket } from '../services/socket';

const sevColor = (s) => ({ critical: 'error', warning: 'warning', info: 'info' }[s] || 'default');

export default function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    try { const r = await api.get('/alerts', { params: { limit: 200 } }); setAlerts(r.data); setError(''); }
    catch (e) { setError(e.response?.data?.msg || 'Failed to load alerts'); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    load();
    const s = getSocket();
    const onAlert = () => load();
    s.on('alert', onAlert);
    return () => s.off('alert', onAlert);
  }, []);

  const ack = async (id) => { try { await api.post(`/alerts/${id}/ack`); load(); } catch (e) { setError(e.response?.data?.msg || 'Failed'); } };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h4">Alerts</Typography><Button onClick={load}>Refresh</Button>
      </Stack>
      {error && <MuiAlert severity="error" sx={{ mb: 2 }}>{error}</MuiAlert>}
      {loading ? <Box sx={{ textAlign: 'center', py: 6 }}><CircularProgress /></Box> : (
        <TableContainer component={Paper}><Table size="small">
          <TableHead><TableRow>
            <TableCell>Severity</TableCell><TableCell>Type</TableCell><TableCell>Message</TableCell><TableCell>Device</TableCell><TableCell>When</TableCell><TableCell align="right">Action</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {alerts.map((a) => (
              <TableRow key={a.id} hover sx={{ opacity: a.acknowledged ? 0.5 : 1 }}>
                <TableCell><Chip size="small" label={a.severity} color={sevColor(a.severity)} /></TableCell>
                <TableCell>{a.type}</TableCell><TableCell>{a.message}</TableCell>
                <TableCell>{a.Device?.hostname || '—'}</TableCell>
                <TableCell>{new Date(a.createdAt).toLocaleString()}</TableCell>
                <TableCell align="right">{a.acknowledged ? <Chip size="small" label="ack" /> : <Button size="small" onClick={() => ack(a.id)}>Ack</Button>}</TableCell>
              </TableRow>
            ))}
            {alerts.length === 0 && <TableRow><TableCell colSpan={6} align="center">No alerts.</TableCell></TableRow>}
          </TableBody>
        </Table></TableContainer>
      )}
    </Box>
  );
}
