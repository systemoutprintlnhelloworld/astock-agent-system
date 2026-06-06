import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(__dirname, "..");
const repoRoot = resolve(frontendRoot, "..", "..");
const desktopDist = join(repoRoot, "apps", "desktop", "dist");
const staticPlaceholder = join(desktopDist, "index.html");

rmSync(desktopDist, { force: true, recursive: true });
mkdirSync(desktopDist, { recursive: true });

const env = { ...process.env, NEXT_PUBLIC_BACKEND_URL: process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000" };
const result = spawnSync("npx", ["next", "build"], { cwd: frontendRoot, env, shell: process.platform === "win32", stdio: "inherit" });
if (result.status !== 0) {
  process.exit(result.status ?? 1);
}

const outDir = join(frontendRoot, "out");

if (existsSync(outDir)) {
  cpSync(outDir, desktopDist, { recursive: true });
}

if (!existsSync(staticPlaceholder)) {
  writeFileSync(
    staticPlaceholder,
    `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AStock Agent Desktop</title></head><body><main style="font-family:system-ui;padding:32px"><h1>AStock Agent Desktop</h1><p>Next.js 静态导出未生成页面。请检查 <code>npm --prefix apps/frontend run build:desktop</code> 输出。</p></main></body></html>`,
    "utf8",
  );
}

console.log(`Desktop frontend assets prepared at ${desktopDist}`);
