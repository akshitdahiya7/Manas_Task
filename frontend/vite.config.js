import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // For `npm run dev`: same relative /api paths as the Docker setup.
    // 127.0.0.1 rather than localhost, which resolves to IPv6 ::1 on Windows
    // and fails against a backend listening on IPv4 only.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
