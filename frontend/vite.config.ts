import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // On this computer "localhost" resolved only to the IPv6 address, so http://127.0.0.1:5173 failed.
    // 127.0.0.1 works for both addresses (browsers fall back from IPv6) and stays private to this computer.
    host: '127.0.0.1',
    // The browser talks only to this dev server; /api calls are passed on to the backend.
    // Same origin, so no CORS configuration is needed.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      // CDR module backends (only active when CDR services are running locally).
      // Set CDR_D1_PORT / CDR_D2_PORT / CDR_D3_PORT in .env to override defaults.
      '/cdr/d1/api': { target: `http://127.0.0.1:${process.env.CDR_D1_PORT ?? '55491'}`, rewrite: (p: string) => p.replace(/^\/cdr\/d1/, '') },
      '/cdr/d2/api': { target: `http://127.0.0.1:${process.env.CDR_D2_PORT ?? '55492'}`, rewrite: (p: string) => p.replace(/^\/cdr\/d2/, '') },
      '/cdr/d3/api': { target: `http://127.0.0.1:${process.env.CDR_D3_PORT ?? '55493'}`, rewrite: (p: string) => p.replace(/^\/cdr\/d3/, '') },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
