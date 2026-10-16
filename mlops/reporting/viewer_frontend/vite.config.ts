import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  root: resolve(__dirname),
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
    minify: true
  }
});
