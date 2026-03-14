#!/usr/bin/env node
/**
 * Entry point for nomadicml-mcp.
 * Resolves the correct pre-compiled binary for the current platform,
 * then spawns it — passing through all stdio so it works as an MCP server.
 */

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

function getPlatformKey() {
  const p = process.platform;
  const a = process.arch;
  if (p === "darwin" && a === "arm64") return "darwin-arm64";
  if (p === "darwin" && a === "x64")   return "darwin-x64";
  if (p === "linux"  && a === "x64")   return "linux-x64";
  if (p === "win32"  && a === "x64")   return "win32-x64";
  throw new Error(
    `Unsupported platform: ${p}/${a}. ` +
    "Please open an issue at https://github.com/nomadic-ml/nomadicml-mcp"
  );
}

function getBinaryPath() {
  const key = getPlatformKey();
  const ext = process.platform === "win32" ? ".exe" : "";
  const binaryName = `nomadicml-mcp-${key}${ext}`;
  const binaryPath = path.join(__dirname, "..", "bin", binaryName);

  if (!fs.existsSync(binaryPath)) {
    throw new Error(
      `Binary not found: ${binaryPath}\n` +
      "Try reinstalling: npx nomadicml-mcp@latest\n" +
      "Or run: node scripts/install.js"
    );
  }
  return binaryPath;
}

try {
  const binary = getBinaryPath();
  const result = spawnSync(binary, process.argv.slice(2), {
    stdio: "inherit",
    env: process.env,
  });
  process.exit(result.status ?? 1);
} catch (err) {
  console.error(`[nomadicml-mcp] ${err.message}`);
  process.exit(1);
}
