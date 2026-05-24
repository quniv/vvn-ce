import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { resolve } from 'node:path'
import { copyFileSync, existsSync, mkdirSync, renameSync } from 'node:fs'

const root = __dirname
const outDir = resolve(root, 'dist')

// Main build: HTML pages (options, game) + service worker.
// Content script is built separately by vite.content.config.ts (self-contained, no chunks).
export default defineConfig({
  plugins: [
    svelte(),
    {
      name: 'finalize-extension-dist',
      closeBundle() {
        // Move HTML files from dist/src/options/options.html → dist/options.html
        const moves: Array<[string, string]> = [
          ['src/options/options.html', 'options.html'],
          ['src/game/game.html', 'game.html'],
        ]
        for (const [from, to] of moves) {
          const src = resolve(outDir, from)
          const dst = resolve(outDir, to)
          if (existsSync(src)) renameSync(src, dst)
        }

        // Copy manifest.json and icons
        copyFileSync(resolve(root, 'manifest.json'), resolve(outDir, 'manifest.json'))
        const publicDir = resolve(root, 'public')
        if (existsSync(publicDir)) {
          for (const f of ['icon-16.png', 'icon-48.png', 'icon-128.png']) {
            const src = resolve(publicDir, f)
            if (existsSync(src)) copyFileSync(src, resolve(outDir, f))
          }
        }
      },
    },
  ],
  build: {
    outDir,
    emptyOutDir: true,
    minify: false,
    rollupOptions: {
      input: {
        'service-worker': resolve(root, 'src/background/service-worker.ts'),
        options: resolve(root, 'src/options/options.html'),
        game: resolve(root, 'src/game/game.html'),
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: (info) => {
          if (info.name?.endsWith('.css')) return 'assets/[name]-[hash][extname]'
          return 'assets/[name][extname]'
        },
      },
    },
  },
})
