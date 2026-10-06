import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

/**
 * Web 包版本号（热更体系，见 src/mobile/updater.js）。
 *
 * 正式发布：scripts/publish_web_update.py 生成 yyyyMMddHHmm 并通过
 * VITE_BUNDLE_VERSION 环境变量注入，保证 dist 内置版本与服务器清单一致。
 * 直接 npm run build（如日常 PC 端构建）：退化为构建时刻的时间戳，仅作标识。
 */
function resolveBundleVersion() {
  const fromEnv = process.env.VITE_BUNDLE_VERSION;
  if (fromEnv) return fromEnv;
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return (
    String(now.getFullYear()) +
    pad(now.getMonth() + 1) +
    pad(now.getDate()) +
    pad(now.getHours()) +
    pad(now.getMinutes())
  );
}

const __BUNDLE_VERSION__ = resolveBundleVersion();

export default defineConfig({
  plugins: [vue()],
  define: {
    __BUNDLE_VERSION__: JSON.stringify(__BUNDLE_VERSION__),
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/bpmn-js") || id.includes("node_modules/diagram-js")) {
            return "bpmn";
          }
          if (id.includes("node_modules/element-plus")) {
            return "element-plus";
          }
          if (id.includes("node_modules/vue") || id.includes("node_modules/vue-router") || id.includes("node_modules/pinia")) {
            return "vue-vendor";
          }
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/geoserver": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
