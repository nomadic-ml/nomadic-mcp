"""
NomadicML MCP Server
Full coverage of the NomadicML Python SDK exposed as MCP tools.
"""

import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP
from nomadicml import NomadicML, OverlayMode, DEFAULT_STRUCTURED_ODD_COLUMNS
from nomadicml.video import AnalysisType, CustomCategory

mcp = FastMCP(
    "nomadicml",
    instructions=(
        "You have access to the NomadicML video analysis platform. "
        "Use upload_video to upload local files or URLs, then analyze_video to run analysis. "
        "For async jobs, poll with get_analysis. "
        "Use list_analysis_options first if unsure what analysis_type or category to use. "
        "Folders help organize videos for batch operations. "
        "Cloud integrations (GCS/S3) let you import directly from cloud buckets."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_client() -> NomadicML:
    api_key = os.environ.get("NOMADICML_API_KEY")
    if not api_key:
        raise ValueError(
            "NOMADICML_API_KEY is not set. "
            "Export it with: export NOMADICML_API_KEY=your_key_here\n"
            "Get your key at: https://app.nomadicml.com → Profile → API Keys"
        )
    base_url = os.environ.get("NOMADICML_BASE_URL", "https://api-prod.nomadicml.com/")
    timeout = int(os.environ.get("NOMADICML_TIMEOUT", "900"))
    return NomadicML(api_key=api_key, base_url=base_url, timeout=timeout)


def _resolve_analysis_type(analysis_type: str) -> AnalysisType:
    try:
        return AnalysisType[analysis_type.upper()]
    except KeyError:
        valid = [e.name for e in AnalysisType
                 if not e.name.startswith(("AGENT_", "LANE_CHANGE_AGENT", "TURN_AGENT",
                                           "RELATIVE_MOTION_AGENT", "VIOLATION_AGENT",
                                           "EDGE_CASE_AGENT"))]
        raise ValueError(
            f"Invalid analysis_type '{analysis_type}'. "
            f"Valid options: {valid}. "
            "Call list_analysis_options() to see descriptions."
        )


def _resolve_category(category: str) -> CustomCategory:
    try:
        return CustomCategory[category.upper()]
    except KeyError:
        valid = [e.name for e in CustomCategory]
        raise ValueError(f"Invalid category '{category}'. Valid options: {valid}")


def _resolve_overlay_mode(mode: Optional[str]) -> Optional[OverlayMode]:
    if not mode:
        return None
    try:
        return OverlayMode[mode.upper()]
    except KeyError:
        valid = [e.name for e in OverlayMode]
        raise ValueError(f"Invalid overlay_mode '{mode}'. Valid options: {valid}")


_NOT_READY_ERRORS = frozenset([
    "analysis document not found",
    "no analysis pointer",
    "did not provide analysis pointer",
])


def _is_terminal(results: list) -> bool:
    """Return True when all per-video results are in a final state."""
    if not results:
        return False
    for r in results:
        status = str(r.get("status", "")).lower()
        if status not in ("completed", "complete", "done", "success", "failed", "error"):
            return False
        # "failed" caused by the doc not being ready yet is NOT terminal
        if status in ("failed", "error"):
            error = str(r.get("error", "")).lower()
            if any(msg in error for msg in _NOT_READY_ERRORS):
                return False
    return True


def _poll_until_done(client: NomadicML, batch_id: str, timeout_seconds: int) -> dict:
    start = time.time()
    interval = 5
    while True:
        result = client.get_batch_analysis(batch_id)
        if _is_terminal(result.get("results", [])):
            return result
        elapsed = time.time() - start
        if elapsed >= timeout_seconds:
            return {"batch_id": batch_id, "status": "timeout",
                    "message": f"Still running after {timeout_seconds}s. "
                               f"Call get_analysis(batch_id='{batch_id}') to check again."}
        time.sleep(interval)
        interval = min(interval * 1.5, 30)


# ---------------------------------------------------------------------------
# 1. Meta / discovery
# ---------------------------------------------------------------------------

@mcp.tool()
def list_analysis_options() -> dict:
    """
    List every valid analysis_type and category supported by NomadicML.
    Call this first when you're unsure which values to use for analyze_video.
    """
    return {
        "analysis_types": {
            "ASK": "Ask any custom question / detect a custom event (rapid review). Requires custom_prompt.",
            "GENERAL_AGENT": "Zero-shot edge-case hunting across the video.",
            "LANE_CHANGE": "Lane-change manoeuvre detection.",
            "TURN": "Left / right turn behaviour detection.",
            "RELATIVE_MOTION": "Relative motion between vehicles.",
            "DRIVING_VIOLATIONS": "Speeding, stop-sign, red-light, and related violations.",
            "CUSTOM_AGENT": "Custom agent pipeline with your own prompt. Requires custom_prompt.",
            "ACTION_SEGMENTATION": "Segment and label actions across the full video timeline.",
        },
        "categories": {
            "DRIVING": "Dashcam / road driving footage.",
            "ROBOTICS": "Robotics and automation footage.",
            "AERIAL": "Drone or aerial footage.",
            "SECURITY": "Security camera footage.",
            "ENVIRONMENT": "Environmental monitoring footage.",
        },
        "overlay_modes": {
            "TIMESTAMPS": "Extract timestamp overlays visible on screen.",
            "GPS": "Extract GPS coordinate overlays visible on screen.",
            "CUSTOM": "Extract custom telemetry fields defined in an uploaded metadata JSON.",
        },
    }


@mcp.tool()
def verify_auth() -> dict:
    """
    Verify that the NOMADICML_API_KEY is valid and the connection works.
    Run this first to confirm setup is correct.
    """
    client = get_client()
    result = client.verify_auth()
    return {"status": "authenticated", "detail": result}


# ---------------------------------------------------------------------------
# 2. Upload
# ---------------------------------------------------------------------------

@mcp.tool()
def upload_video(
    path_or_url: str,
    name: Optional[str] = None,
    folder: Optional[str] = None,
    scope: str = "user",
    metadata_file: Optional[str] = None,
) -> dict:
    """
    Upload a single video to NomadicML.

    Args:
        path_or_url:   Local file path (/Users/me/clip.mp4) or HTTPS URL.
                       Also accepts cloud URIs: gs://bucket/file.mp4 or s3://bucket/file.mp4
        name:          Optional human-readable display name (e.g. "Morning Commute").
        folder:        Folder to upload into. Created automatically if it doesn't exist.
        scope:         'user' (personal, default) or 'org' (shared with your organisation).
        metadata_file: Path to a JSON sidecar file describing overlay fields.
                       Must share the same base filename as the video.

    Returns a dict with video_id and status.
    """
    client = get_client()

    is_local = not (
        path_or_url.startswith("http://")
        or path_or_url.startswith("https://")
        or path_or_url.startswith("gs://")
        or path_or_url.startswith("s3://")
    )

    if is_local:
        file_path = Path(path_or_url).expanduser().resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"Video file not found: {file_path}")
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        mime, _ = mimetypes.guess_type(str(file_path))
        if mime and not mime.startswith("video/"):
            raise ValueError(f"File does not appear to be a video (detected: {mime})")
        upload_target = str(file_path)
    else:
        upload_target = path_or_url

    kwargs: dict = {}
    if name:
        kwargs["name"] = name
    if folder:
        kwargs["folder"] = folder
    if scope:
        kwargs["scope"] = scope
    if metadata_file:
        meta_path = Path(metadata_file).expanduser().resolve()
        if not meta_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {meta_path}")
        upload_target = (upload_target, str(meta_path))

    result = client.upload(upload_target, **kwargs)
    return {
        "video_id": result["video_id"],
        "status": result.get("status"),
        "message": f"Uploaded successfully. Use video_id='{result['video_id']}' to analyze.",
    }


@mcp.tool()
def upload_videos_batch(
    paths_or_urls: list[str],
    folder: Optional[str] = None,
    scope: str = "user",
) -> dict:
    """
    Upload multiple videos in a single batch call.

    Args:
        paths_or_urls: List of local paths, HTTPS URLs, or cloud URIs (gs:// / s3://).
        folder:        Folder to upload into (created if missing).
        scope:         'user' or 'org'.

    Returns a list of {video_id, status} dicts and a summary.
    """
    client = get_client()

    resolved = []
    for p in paths_or_urls:
        is_local = not (p.startswith("http") or p.startswith("gs://") or p.startswith("s3://"))
        if is_local:
            fp = Path(p).expanduser().resolve()
            if not fp.exists():
                raise FileNotFoundError(f"File not found: {fp}")
            resolved.append(str(fp))
        else:
            resolved.append(p)

    kwargs: dict = {}
    if folder:
        kwargs["folder"] = folder
    if scope:
        kwargs["scope"] = scope

    results = client.upload(resolved, **kwargs)
    if not isinstance(results, list):
        results = [results]

    return {
        "uploaded": len(results),
        "videos": [{"video_id": r["video_id"], "status": r.get("status")} for r in results],
        "message": f"Uploaded {len(results)} videos. Pass the video_ids to analyze_video or analyze_folder.",
    }


# ---------------------------------------------------------------------------
# 3. Analyze
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_video(
    video_id: str,
    analysis_type: str,
    category: str = "DRIVING",
    custom_prompt: str = "",
    is_thumbnail: bool = False,
    overlay_mode: Optional[str] = None,
    use_enhanced_motion_analysis: bool = False,
    confidence: str = "low",
    wait: bool = True,
    timeout_seconds: int = 1800,
) -> dict:
    """
    Run analysis on a single uploaded video.

    Args:
        video_id:       From upload_video.
        analysis_type:  e.g. 'LANE_CHANGE', 'ASK', 'DRIVING_VIOLATIONS'. Call list_analysis_options() for all values.
        category:       'DRIVING' (default), 'ROBOTICS', 'AERIAL', 'SECURITY', 'ENVIRONMENT'.
        custom_prompt:  Required when analysis_type is 'ASK' or 'CUSTOM_AGENT'.
        is_thumbnail:   If True, each event includes an annotated_thumbnail_url.
        overlay_mode:   'TIMESTAMPS', 'GPS', or 'CUSTOM' — extracts telemetry from on-screen overlays.
                        Only works if the video was uploaded with a metadata sidecar JSON.
        use_enhanced_motion_analysis: Generate enhanced motion captions for events.
        confidence:     'low' (default, more events) or 'high' (fewer, higher-precision events).
        wait:           Poll until complete (default True). Set False to return immediately.
        timeout_seconds: Max polling time when wait=True. Default 300s.
    """
    client = get_client()
    a_type = _resolve_analysis_type(analysis_type)
    o_mode = _resolve_overlay_mode(overlay_mode)

    kwargs: dict = {
        "analysis_type": a_type,
        "is_thumbnail": is_thumbnail,
        "use_enhanced_motion_analysis": use_enhanced_motion_analysis,
        "confidence": confidence,
        "timeout": timeout_seconds,
    }
    # custom_category is only accepted by the SDK for ASK analysis
    if a_type == AnalysisType.ASK:
        kwargs["custom_category"] = _resolve_category(category)
    if custom_prompt:
        kwargs["custom_event"] = custom_prompt
    if o_mode:
        kwargs["overlay_mode"] = o_mode

    if wait:
        # Let the SDK handle polling natively; pass single video_id for a clean result dict
        return client.analyze(video_id, wait_for_completion=True, **kwargs)

    # For wait=False, pass as a list so the SDK returns a batch_id for manual polling
    result = client.analyze([video_id], wait_for_completion=False, **kwargs)
    batch_id = result.get("batch_metadata", {}).get("batch_id")
    return {"video_id": video_id, "status": "started",
            "batch_id": batch_id,
            "message": f"Analysis started. Call get_analysis(batch_id='{batch_id}') to poll."}


@mcp.tool()
def analyze_videos_batch(
    video_ids: list[str],
    analysis_type: str,
    category: str = "DRIVING",
    custom_prompt: str = "",
    is_thumbnail: bool = False,
    overlay_mode: Optional[str] = None,
    confidence: str = "low",
) -> dict:
    """
    Run the same analysis across multiple video IDs in one batch call.

    Args:
        video_ids:     List of video IDs to analyze.
        analysis_type: e.g. 'LANE_CHANGE', 'ASK', 'DRIVING_VIOLATIONS'.
        category:      'DRIVING', 'ROBOTICS', 'AERIAL', 'SECURITY', 'ENVIRONMENT'.
        custom_prompt: Required when analysis_type is 'ASK' or 'CUSTOM_AGENT'.
        is_thumbnail:  Generate annotated thumbnails per event.
        overlay_mode:  'TIMESTAMPS', 'GPS', or 'CUSTOM'.
        confidence:    'low' or 'high'.

    Returns batch_metadata (including batch_id and batch_viewer_url) plus per-video results.
    """
    client = get_client()
    a_type = _resolve_analysis_type(analysis_type)
    o_mode = _resolve_overlay_mode(overlay_mode)

    kwargs: dict = {
        "analysis_type": a_type,
        "is_thumbnail": is_thumbnail,
        "confidence": confidence,
    }
    if a_type == AnalysisType.ASK:
        kwargs["custom_category"] = _resolve_category(category)
    if custom_prompt:
        kwargs["custom_event"] = custom_prompt
    if o_mode:
        kwargs["overlay_mode"] = o_mode

    result = client.analyze(video_ids, **kwargs)
    return result


@mcp.tool()
def analyze_folder(
    folder: str,
    analysis_type: str,
    category: str = "DRIVING",
    custom_prompt: str = "",
    scope: str = "user",
    confidence: str = "low",
) -> dict:
    """
    Run analysis on every video in a folder in one call.

    Args:
        folder:        Folder name to analyze.
        analysis_type: e.g. 'LANE_CHANGE', 'DRIVING_VIOLATIONS', 'ASK'.
        category:      'DRIVING', 'ROBOTICS', 'AERIAL', 'SECURITY', 'ENVIRONMENT'.
        custom_prompt: Required when analysis_type is 'ASK' or 'CUSTOM_AGENT'.
        scope:         'user' or 'org'.
        confidence:    'low' or 'high'.

    Returns batch_metadata and per-video results.
    """
    client = get_client()
    a_type = _resolve_analysis_type(analysis_type)

    kwargs: dict = {
        "analysis_type": a_type,
        "confidence": confidence,
    }
    if a_type == AnalysisType.ASK:
        kwargs["custom_category"] = _resolve_category(category)
    if custom_prompt:
        kwargs["custom_event"] = custom_prompt

    result = client.analyze(folder=folder, **kwargs)
    return result


# ---------------------------------------------------------------------------
# 4. Get analysis / results
# ---------------------------------------------------------------------------

@mcp.tool()
def get_analysis(
    batch_id: str,
    wait: bool = True,
    timeout_seconds: int = 1800,
) -> dict:
    """
    Retrieve analysis results for a batch (including single-video batches from analyze_video).

    Args:
        batch_id:        From analyze_video / analyze_videos_batch.
        wait:            Poll until complete (default True).
        timeout_seconds: Max wait time. Default 300s.
    """
    client = get_client()
    if not wait:
        return client.get_batch_analysis(batch_id)
    return _poll_until_done(client, batch_id, timeout_seconds)


@mcp.tool()
def get_batch_analysis(
    batch_id: str,
    filter_status: Optional[str] = None,
) -> dict:
    """
    Retrieve results for a completed batch analysis.

    Args:
        batch_id:      The batch_id from analyze_videos_batch or analyze_folder results.
        filter_status: Optional filter — 'approved', 'rejected', 'pending', or 'invalid'.
                       If omitted, all events are returned.

    Returns batch_metadata (including batch_viewer_url) and per-video results.
    """
    client = get_client()
    kwargs: dict = {}
    if filter_status:
        valid = {"approved", "rejected", "pending", "invalid"}
        if filter_status.lower() not in valid:
            raise ValueError(f"Invalid filter_status '{filter_status}'. Valid: {sorted(valid)}")
        kwargs["filter"] = filter_status.lower()
    return client.get_batch_analysis(batch_id, **kwargs)


@mcp.tool()
def add_batch_metadata(
    batch_id: str,
    metadata: dict,
) -> dict:
    """
    Add or update custom key-value metadata on a batch analysis.
    Useful for tagging batches with experiment IDs, versions, notes, etc.

    Args:
        batch_id: The batch to update.
        metadata: Dict with string keys and string/int values (no nesting).
                  Example: {"experiment_id": "exp-001", "version": 2}
    """
    client = get_client()
    return client.add_batch_metadata(batch_id, metadata)


# ---------------------------------------------------------------------------
# 5. Thumbnails / visuals
# ---------------------------------------------------------------------------

@mcp.tool()
def get_visuals(video_id: str, analysis_id: str) -> list:
    """
    Get thumbnail URLs for all events in an analysis.
    Thumbnails are auto-generated if they don't exist yet.

    Args:
        video_id:    Video ID.
        analysis_id: Analysis ID (from analyze_video / get_analysis results).

    Returns a list of thumbnail URL strings.
    """
    client = get_client()
    return client.get_visuals(video_id, analysis_id)


@mcp.tool()
def get_visual(video_id: str, analysis_id: str, event_index: int) -> str:
    """
    Get the thumbnail URL for a single event by its index.

    Args:
        video_id:    Video ID.
        analysis_id: Analysis ID.
        event_index: 0-based index of the event.

    Returns a single thumbnail URL string.
    """
    client = get_client()
    return client.get_visual(video_id, analysis_id, event_index)


# ---------------------------------------------------------------------------
# 6. Search
# ---------------------------------------------------------------------------

@mcp.tool()
def search_videos(
    query: str,
    folder_name: str,
    scope: str = "user",
) -> dict:
    """
    Semantic search across all analysed events inside a folder.
    Returns a chain-of-thought summary, reasoning steps, and matching events.

    Args:
        query:       Natural language query. e.g. "red pickup truck overtaking dangerously"
        folder_name: Folder to search within.
        scope:       'user' (default), 'org', or 'sample'.

    Returns summary, thoughts (reasoning chain), matches, and session_id.
    """
    client = get_client()
    return client.search(query=query, folder_name=folder_name, scope=scope)


# ---------------------------------------------------------------------------
# 7. Video management
# ---------------------------------------------------------------------------

@mcp.tool()
def list_videos(
    folder: Optional[str] = None,
    scope: Optional[str] = None,
) -> list:
    """
    List your uploaded videos, optionally filtered by folder.

    Args:
        folder: Optional folder name to filter by.
        scope:  'user' or 'org' — disambiguates when personal and org folders share a name.

    Returns a list of video dicts with video_id, video_name, duration_s, status, folder_name.
    """
    client = get_client()
    kwargs: dict = {}
    if folder:
        kwargs["folder"] = folder
    if scope:
        kwargs["scope"] = scope
    return client.my_videos(**kwargs)


@mcp.tool()
def delete_video(video_id: str) -> dict:
    """
    Permanently delete a video by ID.

    Args:
        video_id: ID of the video to delete.
    """
    client = get_client()
    return client.delete_video(video_id)


# ---------------------------------------------------------------------------
# 8. Folder management
# ---------------------------------------------------------------------------

@mcp.tool()
def create_folder(
    name: str,
    scope: str = "user",
    description: Optional[str] = None,
) -> dict:
    """
    Create a new folder. Raises an error if a folder with that name already exists.

    Args:
        name:        Folder name (unique within each scope).
        scope:       'user' (default) or 'org'.
        description: Optional description.
    """
    client = get_client()
    kwargs: dict = {"scope": scope}
    if description:
        kwargs["description"] = description
    return client.create_folder(name, **kwargs)


@mcp.tool()
def get_or_create_folder(
    name: str,
    scope: str = "user",
    description: Optional[str] = None,
) -> dict:
    """
    Get a folder if it exists, or create it if it doesn't.
    Safer than create_folder when you're not sure if it already exists.

    Args:
        name:        Folder name.
        scope:       'user' or 'org'.
        description: Optional description (used only on creation).
    """
    client = get_client()
    kwargs: dict = {"scope": scope}
    if description:
        kwargs["description"] = description
    return client.create_or_get_folder(name, **kwargs)


@mcp.tool()
def get_folder(
    name: str,
    scope: str = "user",
) -> dict:
    """
    Look up a folder by name.

    Args:
        name:  Folder name.
        scope: 'user' (default) or 'org'.

    Returns folder id, name, video_count, created_at, and description.
    """
    client = get_client()
    return client.get_folder(name, scope=scope)


# ---------------------------------------------------------------------------
# 9. Structured ODD export
# ---------------------------------------------------------------------------

@mcp.tool()
def generate_structured_odd(
    video_id: str,
    use_default_columns: bool = True,
    custom_columns_json: Optional[str] = None,
) -> dict:
    """
    Generate an ASAM OpenODD-compliant CSV describing the vehicle's operating domain.

    Args:
        video_id:             ID of the analyzed video.
        use_default_columns:  Use NomadicML's default ODD schema (True by default).
        custom_columns_json:  JSON string defining custom columns if use_default_columns=False.
                              Format: [{"name": "...", "prompt": "...", "type": "categorical",
                                        "literals": ["a", "b"]}]

    Returns csv text, share_url, columns, and processing_time.
    """
    client = get_client()

    if use_default_columns:
        columns = DEFAULT_STRUCTURED_ODD_COLUMNS
    else:
        if not custom_columns_json:
            raise ValueError("custom_columns_json is required when use_default_columns=False.")
        try:
            columns = json.loads(custom_columns_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"custom_columns_json is not valid JSON: {e}")

    return client.generate_structured_odd(video_id=video_id, columns=columns)


# ---------------------------------------------------------------------------
# 10. Cloud integrations (GCS / S3)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_cloud_integrations(provider: Optional[str] = None) -> list:
    """
    List saved cloud storage integrations (GCS and/or S3).

    Args:
        provider: Optional filter — 'gcs' or 's3'. Returns all if omitted.

    Returns a list of integration dicts with id, name, type, bucket, prefix.
    """
    client = get_client()
    kwargs: dict = {}
    if provider:
        if provider.lower() not in ("gcs", "s3"):
            raise ValueError("provider must be 'gcs' or 's3'.")
        kwargs["type"] = provider.lower()
    return client.cloud_integrations.list(**kwargs)


@mcp.tool()
def add_gcs_integration(
    name: str,
    bucket: str,
    credentials_file: str,
    prefix: Optional[str] = None,
) -> dict:
    """
    Add a Google Cloud Storage integration using a service-account JSON key file.

    Args:
        name:             A friendly name for this integration (e.g. "Fleet bucket").
        bucket:           GCS bucket name (e.g. "drive-monitor").
        credentials_file: Local path to the service-account JSON key file.
                          Generate one at GCP Console → IAM → Service Accounts → Keys.
                          The account needs Storage Object Viewer + Storage Legacy Bucket Reader.
        prefix:           Optional path prefix within the bucket (e.g. "uploads/fleet/").

    Returns the created integration dict.
    """
    client = get_client()
    creds_path = Path(credentials_file).expanduser().resolve()
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {creds_path}\n"
            "Generate a JSON key at: GCP Console → IAM & Admin → Service Accounts → Keys."
        )
    kwargs: dict = {
        "type": "gcs",
        "name": name,
        "bucket": bucket,
        "credentials": str(creds_path),
    }
    if prefix:
        kwargs["prefix"] = prefix
    return client.cloud_integrations.add(**kwargs)


@mcp.tool()
def add_s3_integration(
    name: str,
    bucket: str,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    prefix: Optional[str] = None,
    session_token: Optional[str] = None,
) -> dict:
    """
    Add an Amazon S3 integration using IAM access keys.

    Args:
        name:              Friendly name (e.g. "AWS archive").
        bucket:            S3 bucket name.
        access_key_id:     IAM access key ID.
        secret_access_key: IAM secret access key.
        region:            AWS region of the bucket (e.g. "us-east-1").
        prefix:            Optional path prefix within the bucket.
        session_token:     Optional temporary session token (for STS credentials).

    The IAM user/role needs s3:ListBucket on the bucket and s3:GetObject on objects.
    Returns the created integration dict.
    """
    client = get_client()
    credentials: dict = {
        "accessKeyId": access_key_id,
        "secretAccessKey": secret_access_key,
    }
    if session_token:
        credentials["sessionToken"] = session_token

    kwargs: dict = {
        "type": "s3",
        "name": name,
        "bucket": bucket,
        "region": region,
        "credentials": credentials,
    }
    if prefix:
        kwargs["prefix"] = prefix

    return client.cloud_integrations.add(**kwargs)


@mcp.tool()
def upload_from_cloud(
    uris: list[str],
    folder: Optional[str] = None,
    scope: str = "user",
    integration_id: Optional[str] = None,
) -> dict:
    """
    Import videos directly from GCS or S3 without downloading them locally.

    Args:
        uris:           List of full cloud URIs:
                        gs://bucket/path/video.mp4
                        s3://bucket/path/video.mp4
        folder:         Folder to place imported videos in.
        scope:          'user' or 'org'.
        integration_id: ID of a saved cloud integration. If omitted, the SDK
                        auto-matches by bucket name — useful if you only have one integration.

    Returns a list of {video_id, status} dicts.
    """
    client = get_client()
    for uri in uris:
        if not (uri.startswith("gs://") or uri.startswith("s3://")):
            raise ValueError(
                f"URI must start with gs:// or s3://. Got: {uri}\n"
                "For HTTPS URLs use upload_video or upload_videos_batch instead."
            )

    kwargs: dict = {}
    if folder:
        kwargs["folder"] = folder
    if scope:
        kwargs["scope"] = scope
    if integration_id:
        kwargs["integration_id"] = integration_id

    results = client.upload(uris, **kwargs)
    if not isinstance(results, list):
        results = [results]

    return {
        "imported": len(results),
        "videos": [{"video_id": r["video_id"], "status": r.get("status")} for r in results],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
