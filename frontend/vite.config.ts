import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev, the panel runs on :5173 and proxies /api to the FastAPI backend on :8000.
// In Docker, FastAPI serves the built panel directly, so no proxy is involved.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
})
