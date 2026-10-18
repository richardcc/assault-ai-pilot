import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'serve-root-assets',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const url = req.url?.split('?')[0] || ''
          if (url.startsWith('/art/')) {
            const rel = decodeURIComponent(url.slice('/art/'.length))
            const file = path.resolve(__dirname, '../assets/art', rel)
            if (fs.existsSync(file) && fs.statSync(file).isFile()) {
              res.setHeader('Cache-Control', 'no-cache')
              return fs.createReadStream(file).pipe(res)
            }
          } else if (url.startsWith('/assets/dice/')) {
            const rel = decodeURIComponent(url.slice('/assets/dice/'.length))
            const file = path.resolve(__dirname, '../assets/art/dice', rel)
            if (fs.existsSync(file) && fs.statSync(file).isFile()) {
              res.setHeader('Cache-Control', 'no-cache')
              return fs.createReadStream(file).pipe(res)
            }
          }
          next()
        })
      }
    }
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:8001',
      '/ws': {
        target: 'ws://localhost:8001',
        ws: true,
      }
    }
  }
})
