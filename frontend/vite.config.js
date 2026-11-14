import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const BACKEND = process.env.FIREGUARD_BACKEND || 'http://localhost:8000'

// Same proxy for `npm run dev` and `npm run preview`, so the browser only ever talks to
// this server - the dashboard then also works from a phone/tablet on the same network.
const proxy = {
  '/api': { target: BACKEND, changeOrigin: true },
  '/ws': { target: BACKEND.replace(/^http/, 'ws'), ws: true },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 3000, proxy },
  preview: { port: 3000, proxy },
})
