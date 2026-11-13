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
    // Same origin, so no CORS configuration is needed. API_PROXY points it at another backend
    // (the browser walk-through runs one on its own throwaway database).
    proxy: { '/api': process.env.API_PROXY ?? 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Screens with many Mantine parts take more than the default 5 s to draw when several test files run at once.
    testTimeout: 20_000,
  },
})
