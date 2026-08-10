import { useState, useEffect } from 'react';
import {
  Box, Typography, Button, Alert, CircularProgress, Chip, Stack,
  Table, TableHead, TableRow, TableCell, TableBody, TableContainer, Paper
} from '@mui/material';
import api from '../services/api';

const Bool = ({ v }) => <Chip size="small" label={v ? 'yes' : 'no'} color={v ? 'success' : 'default'} />;

export default function Monitoring() {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState({});
  const [results, setResults] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get('/devices', { params: { limit: 200 } });
      setDevices(r.data.data);
      setError('');
    } catch (e) { setError(e.response?.data?.msg || 'Failed to load devices'); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const runCheck = async (id) => {
    setChecking((c) => ({ ...c, [id]: true }));
    try {
      const r = await api.post(`/devices/${id}/health-check`);
      setResults((res) => ({ ...res, [id]: r.data }));
    } catch (e) {
      setResults((res) => ({ ...res, [id]: { error: e.response?.data?.msg || 'check failed' } }));
    } finally {
      setChecking((c) => ({ ...c, [id]: false }));
    }
  };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h4">Monitoring</Typography>
        <Button onClick={load}>Refresh</Button>
      </Stack>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {loading ? <Box sx={{ textAlign: 'center', py: 6 }}><CircularProgress /></Box> : (
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Hostname</TableCell><TableCell>IP</TableCell><TableCell>Status</TableCell>
                <TableCell>Ping</TableCell><TableCell>SSH</TableCell><TableCell>SNMP</TableCell>
                <TableCell>RTT (ms)</TableCell><TableCell align="right">Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {devices.map((d) => {
                const r = results[d.id];
                return (
                  <TableRow key={d.id} hover>
                    <TableCell>{d.hostname}</TableCell>
                    <TableCell>{d.ip_address}</TableCell>
                    <TableCell><Chip size="small" label={d.status} /></TableCell>
                    <TableCell>{r ? <Bool v={r.ping} /> : '—'}</TableCell>
                    <TableCell>{r ? <Bool v={r.ssh} /> : '—'}</TableCell>
                    <TableCell>{r ? <Bool v={r.snmp} /> : '—'}</TableCell>
                    <TableCell>{r?.response_time_ms ?? '—'}</TableCell>
                    <TableCell align="right">
                      <Button size="small" disabled={checking[d.id]} onClick={() => runCheck(d.id)}>
                        {checking[d.id] ? 'Checking…' : 'Run Check'}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
              {devices.length === 0 && <TableRow><TableCell colSpan={8} align="center">No devices.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
