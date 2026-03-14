# nomadicml-mcp

Full-coverage MCP server for [NomadicML](https://nomadicml.com) — expose every SDK capability to Claude Code and Claude.ai agents.

## Installation

```bash
pip install nomadicml-mcp
```

## Setup

```bash
# 1. Set your API key
export NOMADICML_API_KEY=your_api_key_here

# 2. Register with Claude Code
claude mcp add nomadicml -- nomadicml-mcp

# 3. Verify it's connected
claude mcp list
```

Get your API key at [app.nomadicml.com](https://app.nomadicml.com) → Profile → API Keys.

## Optional environment variables

| Variable | Default | Description |
|---|---|---|
| `NOMADICML_API_KEY` | — | **Required.** Your NomadicML API key. |
| `NOMADICML_BASE_URL` | `https://api-prod.nomadicml.com/` | Override for VPC / self-hosted setups. |
| `NOMADICML_TIMEOUT` | `900` | Request timeout in seconds. |

## All available tools

### Meta
| Tool | Description |
|---|---|
| `verify_auth` | Check that your API key works. Run this first. |
| `list_analysis_options` | List all valid analysis_type and category values. |

### Upload
| Tool | Description |
|---|---|
| `upload_video` | Upload a single local file, HTTPS URL, or cloud URI (gs:// / s3://). |
| `upload_videos_batch` | Upload multiple videos in one call. |
| `upload_from_cloud` | Import directly from GCS or S3 using saved cloud integrations. |

### Analyze
| Tool | Description |
|---|---|
| `analyze_video` | Run analysis on a single video. Polls until complete by default. |
| `analyze_videos_batch` | Run the same analysis on multiple video IDs. |
| `analyze_folder` | Run analysis on every video in a folder. |

### Results
| Tool | Description |
|---|---|
| `get_analysis` | Poll for single-video analysis results. |
| `get_batch_analysis` | Retrieve batch results, optionally filtered by approval status. |
| `add_batch_metadata` | Tag a batch with custom key-value metadata. |

### Thumbnails
| Tool | Description |
|---|---|
| `get_visuals` | Get all thumbnail URLs for an analysis. Auto-generates if missing. |
| `get_visual` | Get a single event thumbnail by index. |

### Search
| Tool | Description |
|---|---|
| `search_videos` | Semantic search across all analysed events in a folder. |

### Video management
| Tool | Description |
|---|---|
| `list_videos` | List uploaded videos, optionally filtered by folder. |
| `delete_video` | Permanently delete a video by ID. |

### Folder management
| Tool | Description |
|---|---|
| `create_folder` | Create a new folder (errors if already exists). |
| `get_or_create_folder` | Get or create a folder safely. |
| `get_folder` | Look up a folder by name. |

### Structured ODD
| Tool | Description |
|---|---|
| `generate_structured_odd` | Generate an ASAM OpenODD-compliant CSV for a video's operating domain. |

### Cloud integrations
| Tool | Description |
|---|---|
| `list_cloud_integrations` | List saved GCS / S3 integrations. |
| `add_gcs_integration` | Add a GCS integration using a service-account JSON key file. |
| `add_s3_integration` | Add an S3 integration using IAM access keys. |

## Analysis types

| Type | Description |
|---|---|
| `ASK` | Ask any custom question — requires `custom_prompt`. |
| `LANE_CHANGE` | Lane-change event detection. |
| `TURN` | Left / right turn detection. |
| `RELATIVE_MOTION` | Relative motion between vehicles. |
| `DRIVING_VIOLATIONS` | Speeding, stop-sign, red-light violations. |
| `GENERAL_AGENT` | Zero-shot edge-case hunting. |
| `CUSTOM_AGENT` | Custom agent pipeline — requires `custom_prompt`. |
| `ACTION_SEGMENTATION` | Segment and label actions across the full timeline. |

## Categories

`DRIVING` · `ROBOTICS` · `AERIAL` · `SECURITY` · `ENVIRONMENT`

## Example Claude Code sessions

**Basic analysis:**
```
> Analyze /Users/me/dashcam/clip.mp4 for driving violations
```

**Batch folder workflow:**
```
> Upload these 3 videos to a folder called "fleet_march" (org scope):
  https://storage.example.com/a.mp4
  https://storage.example.com/b.mp4
  https://storage.example.com/c.mp4
  Then find all near-miss events in that folder.
```

**Search after analysis:**
```
> Search the "fleet_march" folder for pedestrian incidents
```

**Cloud import:**
```
> Import gs://my-fleet-bucket/trips/2024-03-01/ into NomadicML
  and run lane change analysis on all of them
```

**Structured ODD export:**
```
> Generate a structured ODD CSV for video vid_abc123
```

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## GCS integration notes

The service account JSON key needs two IAM roles on your bucket:
- `Storage Object Viewer`
- `Storage Legacy Bucket Reader`

Generate the key at: GCP Console → IAM & Admin → Service Accounts → your account → Keys → Add Key → JSON.

## S3 integration notes

The IAM user/role needs:
- `s3:ListBucket` on the bucket
- `s3:GetObject` on the objects/prefix

Minimum IAM policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": "s3:ListBucket",
     "Resource": "arn:aws:s3:::your-bucket"},
    {"Effect": "Allow", "Action": "s3:GetObject",
     "Resource": "arn:aws:s3:::your-bucket/*"}
  ]
}
```
# nomadic-mcp
