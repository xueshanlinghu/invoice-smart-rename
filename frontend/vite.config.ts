import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

const frontendRoot = fileURLToPath(new URL(".", import.meta.url));
const projectRoot = path.resolve(frontendRoot, "..");

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, projectRoot, "");
  const backendHost = env.APP_HOST || "127.0.0.1";
  const backendPort = env.APP_PORT || "8765";
  const apiBaseUrl = env.VITE_API_BASE_URL || `http://${backendHost}:${backendPort}`;
  const webHost = env.VITE_DEV_SERVER_HOST || "127.0.0.1";
  const webPort = Number.parseInt(env.VITE_DEV_SERVER_PORT || "5173", 10);
  const safeWebPort = Number.isFinite(webPort) && webPort > 0 ? webPort : 5173;

  return {
    root: frontendRoot,
    envDir: projectRoot,
    plugins: [vue()],
    define: {
      __APP_DEFAULT_API_BASE__: JSON.stringify(apiBaseUrl),
    },
    server: {
      host: webHost,
      port: safeWebPort,
      strictPort: true,
    },
  };
});
