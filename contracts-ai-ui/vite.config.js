import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const host = process.env.TAURI_DEV_HOST;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5174,
    strictPort: false,  // Allow fallback to next available port
    host: host || false,
    hmr: host
      ? {
        protocol: "ws",
        host,
        port: 5175,
      }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
});
