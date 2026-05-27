import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "path";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 8888,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            const ct = proxyRes.headers["content-type"] || "";
            if (ct.includes("text/event-stream")) {
              proxyRes.headers["Cache-Control"] = "no-cache";
              proxyRes.headers["X-Accel-Buffering"] = "no";
            }
          });
        },
      },
      "/v1": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
