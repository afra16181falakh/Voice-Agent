import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Vite blocks unrecognized Host headers by default (DNS-rebinding
    // protection) -- an ngrok tunnel's Host header won't match localhost,
    // so it gets rejected ("Blocked request...") without this. Allowing
    // ngrok's domains broadly rather than one specific subdomain since the
    // tunnel URL can change between sessions on the free tier.
    allowedHosts: ['.ngrok-free.dev', '.ngrok-free.app', '.ngrok.io', '.ngrok.app'],
    // Proxies API/WebSocket calls to the local backend so a single tunnel
    // (ngrok etc.) exposing only this dev server is enough for a fully
    // functional remote demo -- the backend itself is never directly
    // reachable from outside this machine. Only active when the frontend
    // is configured to use relative URLs (VITE_API_BASE unset/empty); has
    // no effect otherwise.
    proxy: {
      '/api': 'http://127.0.0.1:8092',
      '/sessions': 'http://127.0.0.1:8092',
      '/health': 'http://127.0.0.1:8092',
      '/ws': {
        target: 'ws://127.0.0.1:8092',
        ws: true,
      },
    },
  },
})
