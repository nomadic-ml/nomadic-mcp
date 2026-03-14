# Publishing nomadicml-mcp to npm

Complete guide to going from code → `npx nomadicml-mcp`.

---

## How it works

```
git tag v0.2.0
      ↓
GitHub Actions builds 4 binaries (macOS arm64, macOS x64, Linux x64, Windows x64)
      ↓
Binaries attached to GitHub Release as assets
      ↓
npm package published (just JS wrapper + install script, no binaries)
      ↓
User runs: npx nomadicml-mcp
      ↓
postinstall script downloads the right binary from GitHub Release
      ↓
bin/run.js spawns the binary
```

---

## One-time setup

### 1. Create an npm account
Go to [npmjs.com](https://npmjs.com) → Sign up.

### 2. Get an npm publish token
```
npmjs.com → Profile → Access Tokens → Generate New Token → Classic Token → Automation
```
Copy the token (starts with `npm_`).

### 3. Add npm token to GitHub Secrets
```
GitHub repo → Settings → Secrets and variables → Actions → New secret
Name:  NPM_TOKEN
Value: npm_your_token_here
```

### 4. Make sure your GitHub repo name matches
The `scripts/install.js` downloads binaries from:
```
https://github.com/nomadic-ml/nomadicml-mcp/releases/...
```
Update `GITHUB_REPO` in `scripts/install.js` if your repo path is different.

---

## Cutting a release

### 1. Bump the version in both files
`package.json`:
```json
"version": "0.2.0"
```
`pyproject.toml` (keep in sync):
```toml
version = "0.2.0"
```

### 2. Update CHANGELOG.md

### 3. Commit and push
```bash
git add package.json pyproject.toml CHANGELOG.md
git commit -m "chore: release v0.2.0"
git push origin main
```

### 4. Tag it
```bash
git tag v0.2.0
git push origin v0.2.0
```

This triggers the GitHub Actions workflow which:
1. Builds all 4 binaries in parallel (~5 min)
2. Creates a GitHub Release with binaries attached
3. Publishes the npm package

### 5. Verify
```bash
# Wait ~10 minutes for all jobs to complete, then:
npx nomadicml-mcp@0.2.0
```

Check npm: `https://www.npmjs.com/package/nomadicml-mcp`

---

## Testing locally before publishing

### Build the binary locally
```bash
pip install pyinstaller
pip install -e .
pyinstaller nomadicml-mcp.spec
```
Binary lands in `dist/`.

### Test the npm package locally
```bash
# Simulate what npx does
node bin/run.js
# or
npm link
nomadicml-mcp
```

### Test the full install flow
```bash
# Pack it as a tarball
npm pack

# Install from tarball in a temp dir
cd /tmp && mkdir test-install && cd test-install
npm install /path/to/nomadicml-mcp-0.2.0.tgz
./node_modules/.bin/nomadicml-mcp
```

---

## User setup after publish

Once on npm, users set up Claude Code with:

```bash
# Option A — register permanently
claude mcp add nomadicml \
  -e NOMADICML_API_KEY=your_key \
  -- npx nomadicml-mcp

# Option B — one-liner for a single session
NOMADICML_API_KEY=your_key npx nomadicml-mcp
```

---

## Troubleshooting

**Binary download fails during install**
The GitHub Release must exist before the npm package is installed.
The workflow creates the release first, then publishes npm — this is guaranteed by `needs: release` in the workflow.

**`npx` uses a cached old version**
```bash
npx --yes nomadicml-mcp@latest
# or clear npx cache:
npx clear-npx-cache
```

**PyInstaller missing hidden imports**
If the binary crashes with `ModuleNotFoundError`, add the missing module to
`hiddenimports` in `nomadicml-mcp.spec` and rebuild.
