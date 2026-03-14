/**
 * Runs after `npm install` (postinstall hook).
 * Downloads the correct pre-compiled binary from GitHub Releases
 * for the current platform and places it in bin/.
 */

const https = require("https");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { execSync } = require("child_process");

const PACKAGE_VERSION = require("../package.json").version;
const GITHUB_REPO = "nomadic-ml/nomadicml-mcp";
const BIN_DIR = path.join(__dirname, "..", "bin");

function getPlatformKey() {
  const p = process.platform;
  const a = process.arch;
  if (p === "darwin" && a === "arm64") return "darwin-arm64";
  if (p === "darwin" && a === "x64")   return "darwin-x64";
  if (p === "linux"  && a === "x64")   return "linux-x64";
  if (p === "win32"  && a === "x64")   return "win32-x64";
  return null;
}

function getBinaryName(key) {
  const ext = process.platform === "win32" ? ".exe" : "";
  return `nomadicml-mcp-${key}${ext}`;
}

function download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    const follow = (u) => {
      https.get(u, (res) => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          follow(res.headers.location);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode} downloading ${u}`));
          return;
        }
        res.pipe(file);
        file.on("finish", () => file.close(resolve));
        file.on("error", reject);
      }).on("error", reject);
    };
    follow(url);
  });
}

async function main() {
  const key = getPlatformKey();
  if (!key) {
    console.warn(
      `[nomadicml-mcp] Unsupported platform ${process.platform}/${process.arch} — skipping binary install.`
    );
    return;
  }

  const binaryName = getBinaryName(key);
  const binaryPath = path.join(BIN_DIR, binaryName);

  // Already installed
  if (fs.existsSync(binaryPath)) {
    console.log(`[nomadicml-mcp] Binary already installed: ${binaryName}`);
    return;
  }

  fs.mkdirSync(BIN_DIR, { recursive: true });

  const url = `https://github.com/${GITHUB_REPO}/releases/download/v${PACKAGE_VERSION}/${binaryName}`;
  console.log(`[nomadicml-mcp] Downloading binary for ${key}...`);
  console.log(`[nomadicml-mcp] ${url}`);

  try {
    await download(url, binaryPath);
    // Make executable on Unix
    if (process.platform !== "win32") {
      fs.chmodSync(binaryPath, 0o755);
    }
    console.log(`[nomadicml-mcp] Installed: ${binaryName}`);
  } catch (err) {
    fs.unlink(binaryPath, () => {});
    console.error(`[nomadicml-mcp] Failed to download binary: ${err.message}`);
    console.error(
      `[nomadicml-mcp] You can download it manually from:\n` +
      `  https://github.com/${GITHUB_REPO}/releases/tag/v${PACKAGE_VERSION}`
    );
    process.exit(1);
  }
}

main();
