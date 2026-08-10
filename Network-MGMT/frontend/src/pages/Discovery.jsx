import { useState } from 'react';
import {
  Box, Typography, Button, TextField, Alert, CircularProgress, Stack,
  Table, TableHead, TableRow, TableCell, TableBody, TableContainer, Paper, Chip
} from '@mui/material';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Discovery() {
  const { user } = useAuth();
  const [network, setNetwork] = useState('192.168.1.0/24');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const run = async () => {
    setRunning(true); setError(''); setResult(null);
    try {
      const r = await api.post('/devices/discover', { network });
      setResult(r.data);
    } catch (e) {
      setError(e.response?.data?.msg || 'Discovery failed (admin role required)');
    } finally { setRunning(false); }
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Network Discovery</Typography>
      {user?.role !== 'admin' && <Alert severity="info" sx={{ mb: 2 }}>Discovery requires the admin role.</Alert>}
      <Stack direction="row" spacing={2} sx={{ mb: 2 }} alignItems="center">
        <TextField label="Network (CIDR)" value={network} onChange={(e) => setNetwork(e.target.value)} sx={{ width: 260 }} />
        <Button variant="contained" onClick={run} disabled={running || !network.trim()}>
          {running ? 'Scanning…' : 'Start Discovery'}
        </Button>
        {running && <CircularProgress size={22} />}
      </Stack>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {result && (
        <>
          <Alert severity="success" sx={{ mb: 2 }}>{result.msg}: {result.devices_found} device(s) found and imported.</Alert>
          <TableContainer component={Paper}>
            <Table size="small">
              <TableHead>
                <TableRow><TableCell>IP</TableCell><TableCell>Hostname</TableCell><TableCell>Vendor</TableCell><TableCell>Type</TableCell><TableCell>SNMP</TableCell></TableRow>
              </TableHead>
              <TableBody>
                {result.devices.map((d) => (
                  <TableRow key={d.ip_address}>
                    <TableCell>{d.ip_address}</TableCell>
                    <TableCell>{d.hostname || '—'}</TableCell>
                    <TableCell>{d.vendor}</TableCell>
                    <TableCell>{d.device_type}</TableCell>
                    <TableCell><Chip size="small" label={d.snmp_responds ? 'yes' : 'no'} color={d.snmp_responds ? 'success' : 'default'} /></TableCell>
                  </TableRow>
                ))}
                {result.devices.length === 0 && <TableRow><TableCell colSpan={5} align="center">No responsive devices found.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}
    </Box>
  );
}
