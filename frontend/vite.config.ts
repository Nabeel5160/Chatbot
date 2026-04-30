import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GitHub Pages project site: CI sets VITE_BASE_PATH=/Chatbot/ (must match repo name, trailing slash).
// Local dev: leave unset → base "/".

// https://vite.dev/config/
export default defineConfig({
  base: process.env.VITE_BASE_PATH?.trim() || '/',
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
