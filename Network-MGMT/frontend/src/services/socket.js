import { io } from 'socket.io-client';
let socket;
export function getSocket() {
  if (!socket) {
    socket = io('/', { path: '/socket.io', transports: ['websocket', 'polling'], auth: { token: localStorage.getItem('token') } });
  }
  return socket;
}
