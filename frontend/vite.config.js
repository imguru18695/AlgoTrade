import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server runs on 5173 and proxies /api to the FastAPI app on 8001.
// Production build emits to dist/ (FastAPI will serve it in a later step).
export default defineConfig({
  plugins: [react()],
  // Served by FastAPI (demo.py) under /app in production; assets resolve to /app/assets/*.
  base: '/app/',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8001',
    },
  },
  build: { outDir: 'dist' },
})
