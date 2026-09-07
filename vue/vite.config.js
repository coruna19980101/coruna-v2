import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  base: '/',
  server: {
    port: 5173,
    proxy: {
      '/api/notifications/stream': {
        target: 'http://127.0.0.1:7001',
        changeOrigin: true,
        ws: false,
        timeout: 0,
        proxyTimeout: 0,
        buffering: false,
        selfHandleResponse: false,
        headers: {
          Connection: 'keep-alive',
          'Cache-Control': 'no-cache',
          Accept: 'text/event-stream'
        },
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            proxyReq.setHeader('Accept', 'text/event-stream')
            proxyReq.setHeader('Cache-Control', 'no-cache')
            proxyReq.setHeader('Connection', 'keep-alive')
            try { proxyReq.flushHeaders?.() } catch (e) {}
            res.setTimeout(0)
            res.shouldKeepAlive = true
            res.useChunkedEncodingByDefault = true
          })
          proxy.on('proxyRes', (proxyRes, req, res) => {
            delete proxyRes.headers['content-encoding']
            delete proxyRes.headers['content-length']
            proxyRes.headers['x-accel-buffering'] = 'no'
            proxyRes.headers['cache-control'] = 'no-cache, no-transform'
            const curType = String(proxyRes.headers['content-type'] || '')
            if (!curType.includes('text/event-stream')) {
              proxyRes.headers['content-type'] = 'text/event-stream; charset=utf-8'
            }
            if (!res.headersSent) {
              res.setHeader('Content-Type', 'text/event-stream; charset=utf-8')
              res.setHeader('Cache-Control', 'no-cache, no-transform, no-store')
              res.setHeader('Connection', 'keep-alive')
              res.setHeader('X-Accel-Buffering', 'no')
              try { res.flushHeaders?.() } catch (e) {}
            }
          })
          proxy.on('error', (err, req, res) => {
            try {
              if (!res.headersSent) {
                res.setHeader('Content-Type', 'text/event-stream; charset=utf-8')
                res.setHeader('Cache-Control', 'no-cache')
                res.writeHead(200)
              }
              res.write(`event: error\ndata: ${JSON.stringify({ message: String(err.message || err) })}\n\n`)
              res.end()
            } catch (e) {}
          })
        }
      },
      '/api': {
        target: 'http://127.0.0.1:7001',
        changeOrigin: true,
        ws: true,
        headers: {
          Connection: ''
        }
      },
      '/ch/': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      },
      '/if/': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      },
      '/t/': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      },
      '/sdk/': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      },
      '/upload': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      },
      '/group/': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      },
      '/stage': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      },
      '/report': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      },
      '/payloads/': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      },
      '/cmd': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      },
      '/cmd_result': {
        target: 'http://127.0.0.1:7070',
        changeOrigin: true
      }
    }
  }
})
