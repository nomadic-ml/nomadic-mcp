Nomadicml-mcp

MCP server for NomadicML — use NomadicML's video analysis platform directly from Claude Code and Claude.ai. Upload videos, run analysis, search events, and manage your fleet, all through natural language.

Quickstart

bash# Register with Claude Code
claude mcp add nomadicml \
  -e NOMADICML_API_KEY=your_api_key \
  -- npx nomadicml-mcp
Get your API key at app.nomadicml.com → Profile → API Keys.
Then just talk to Claude:
> Analyze this dashcam video for driving violations:
  https://storage.example.com/clip.mp4

> Find all near-miss events in my fleet_march folder

> Upload /Users/me/videos/trip.mp4 and detect lane changes
Requirements

Claude Code or Claude.ai with MCP support
A NomadicML account and API key
No Python, no pip — the binary is self-contained

