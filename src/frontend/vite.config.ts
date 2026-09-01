import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

const backendProxyTarget = process.env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:3001'
const backendWebSocketTarget = backendProxyTarget.replace(/^http/, 'ws')

const cloudOnlyModules = [
  '/src/main-portal.tsx',
  '/src/AppPortal.tsx',
  '/src/routes-portal.tsx',
  '/src/pages/portal/',
  '/src/pages/admin/TemplateManagerPage.tsx',
  '/src/pages/admin/AdminOrdersPage.tsx',
  '/src/pages/admin/AdminSubscriptionsPage.tsx',
  '/src/lib/portalApi.ts',
  '/src/components/portal/',
]

function coreBoundaryPlugin(): Plugin {
  return {
    name: 'mchat-core-boundary',
    generateBundle() {
      const leaked = [...this.getModuleIds()]
        .map((id) => id.split('?', 1)[0].replaceAll('\\', '/'))
        .filter((id) => cloudOnlyModules.some((segment) => id.includes(segment)))
      if (leaked.length > 0) {
        this.error(`Core build imported Cloud-only modules:\n${leaked.sort().join('\n')}`)
      }
    },
  }
}

export default defineConfig({
  plugins: [coreBoundaryPlugin(), tailwindcss(), react()],
  resolve: {
    alias: [{ find: '@', replacement: path.resolve(__dirname, './src') }],
  },
  server: {
    host: process.env.VITE_DEV_HOST || '0.0.0.0',
    port: Number(process.env.VITE_DEV_PORT || 5173),
    strictPort: true,
    proxy: {
      '/api': {
        target: backendProxyTarget,
        changeOrigin: true,
      },
      '/uploads': {
        target: backendProxyTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: backendWebSocketTarget,
        ws: true,
      },
      '/go': {
        target: backendProxyTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        widget: path.resolve(__dirname, 'widget.html'),
        'wx-mini': path.resolve(__dirname, 'wx-mini.html'),
      },
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
          markdown: ['react-markdown', 'remark-gfm', 'react-syntax-highlighter'],
        },
      },
    },
  },
})
