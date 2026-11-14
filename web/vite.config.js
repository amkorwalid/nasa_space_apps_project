import { defineConfig } from 'vite';

// Relative base so the static build works on GitHub Pages / Netlify sub-paths.
export default defineConfig({
  base: './',
  // MapLibre alone is ~1 MB minified; that's expected for a map app.
  build: { chunkSizeWarningLimit: 1600 },
});
