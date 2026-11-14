import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Backend przepuszcza w CORS tylko http://localhost:5173. strictPort: gdy port jest
    // zajęty, Vite zgłasza błąd zamiast po cichu przejść na 5174 (wtedy CORS by blokował).
    port: 5173,
    strictPort: true,
    // Proxy: przeglądarka woła /api/... na porcie 5173, a Vite przekazuje to do backendu.
    // Frontend nie musi znać adresu backendu, a w trybie dev nie ma problemów z CORS.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
