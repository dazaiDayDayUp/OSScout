import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        // Docker 环境中通过环境变量指定后端地址，默认 localhost 用于宿主机开发
        target: process.env.VITE_API_PROXY_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
