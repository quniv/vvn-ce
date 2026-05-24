import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { resolve } from 'node:path'

const root = __dirname

// Separate build for the content script — must be a SINGLE self-contained
// IIFE bundle (no ES module imports, since content scripts run as classic scripts).
export default defineConfig({
  plugins: [svelte()],
  build: {
    outDir: resolve(root, 'dist'),
    emptyOutDir: false, // do not wipe the main build output
    minify: false,
    lib: {
      entry: resolve(root, 'src/content/content-script.ts'),
      formats: ['iife'],
      name: 'VocabCEContentScript',
      fileName: () => 'content-script.js',
    },
    rollupOptions: {
      output: {
        // IIFE format forces single bundle with inlined imports
        inlineDynamicImports: true,
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
})
