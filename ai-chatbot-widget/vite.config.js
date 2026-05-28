import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    cors: true,
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    // Optimize for iframe embedding
    rollupOptions: {
      output: {
        manualChunks: undefined,
      },
    },
  },
})
