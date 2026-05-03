import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/auth': 'http://127.0.0.1:8000',
      '/users': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/dataset': 'http://127.0.0.1:8000',
      '/recommend': 'http://127.0.0.1:8000',
      '/train': 'http://127.0.0.1:8000',
      '/evaluate': 'http://127.0.0.1:8000',
      // Add WebSocket proxy to support live recommendations
      // This forwards ws://localhost:5173/ws/* to ws://127.0.0.1:8001/ws/*
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
})
