import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server runs on 5173 and proxies the backend's own routes to the
// FastAPI app on 8001. Every prefix the frontend calls directly (not just
// /api's GETs — postForm's mutations hit /baskets, /logs/clear, /pnl bare)
// needs an entry here, or that call silently 404s against Vite's own static
// server instead of reaching FastAPI at all.
// Production build emits to dist/ (FastAPI will serve it in a later step).
export default defineConfig({
  plugins: [react()],
  // Relative base so the same build works mounted at "/" (main.py, the live
  // domain) or "/app" (demo.py) without a rebuild — asset URLs resolve relative
  // to wherever index.html itself is served from.
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8001',
      '/baskets': 'http://localhost:8001',
      '/logs': 'http://localhost:8001',
      '/pnl': 'http://localhost:8001',
    },
  },
  build: { outDir: 'dist' },
})
