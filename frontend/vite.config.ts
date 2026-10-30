import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In production Vercel serves the app and routes /api/* to the Python function (same origin).
// Locally, Vite proxies /api to uvicorn so the code is identical.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
  build: {
    chunkSizeWarningLimit: 900,
  },
})
