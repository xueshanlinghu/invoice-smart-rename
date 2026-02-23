import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

function parseDotEnv(filePath) {
  try {
    const text = readFileSync(filePath, "utf-8");
    const result = {};
    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) continue;
      const equalAt = line.indexOf("=");
      if (equalAt <= 0) continue;
      const key = line.slice(0, equalAt).trim();
      let value = line.slice(equalAt + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"'))
        || (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      result[key] = value;
    }
    return result;
  } catch {
    return {};
  }
}

const projectRoot = process.cwd();
const env = parseDotEnv(path.join(projectRoot, ".env"));
const webHost = env.VITE_DEV_SERVER_HOST || "127.0.0.1";
const webPort = env.VITE_DEV_SERVER_PORT || "5173";
const devUrl = `http://${webHost}:${webPort}`;

const override = {
  build: {
    beforeDevCommand: "npm run dev:web",
    devUrl,
  },
};

const tempDir = mkdtempSync(path.join(tmpdir(), "invoice-tauri-dev-"));
const overridePath = path.join(tempDir, "tauri.dev.override.json");
writeFileSync(overridePath, JSON.stringify(override), "utf-8");

const npxCmd = process.platform === "win32" ? "npx.cmd" : "npx";
const child = spawn(npxCmd, ["tauri", "dev", "--config", overridePath], {
  stdio: "inherit",
  cwd: projectRoot,
  env: process.env,
});

child.on("exit", (code, signal) => {
  rmSync(tempDir, { recursive: true, force: true });
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
