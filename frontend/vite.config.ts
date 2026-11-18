import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Em desenvolvimento, /api é encaminhado ao backend (mesmo contrato do nginx em produção).
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_URL ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
