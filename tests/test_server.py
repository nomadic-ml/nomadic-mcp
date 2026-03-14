import json
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setenv("NOMADICML_API_KEY", "test_key_123")


@pytest.fixture()
def mock_client():
    with patch("nomadicml_mcp.server.NomadicML") as cls:
        client = MagicMock()
        cls.return_value = client
        yield client


# ---------------------------------------------------------------------------
# verify_auth
# ---------------------------------------------------------------------------

def test_verify_auth(mock_client):
    mock_client.verify_auth.return_value = {"user": "test@example.com"}
    from nomadicml_mcp.server import verify_auth
    result = verify_auth()
    assert result["status"] == "authenticated"


# ---------------------------------------------------------------------------
# list_analysis_options
# ---------------------------------------------------------------------------

def test_list_analysis_options():
    from nomadicml_mcp.server import list_analysis_options
    result = list_analysis_options()
    assert "ASK" in result["analysis_types"]
    assert "LANE_CHANGE" in result["analysis_types"]
    assert "DRIVING" in result["categories"]
    assert "TIMESTAMPS" in result["overlay_modes"]


# ---------------------------------------------------------------------------
# upload_video
# ---------------------------------------------------------------------------

def test_upload_video_url(mock_client):
    mock_client.upload.return_value = {"video_id": "vid_abc", "status": "uploaded"}
    from nomadicml_mcp.server import upload_video
    result = upload_video("https://example.com/video.mp4")
    assert result["video_id"] == "vid_abc"
    mock_client.upload.assert_called_once_with("https://example.com/video.mp4", scope="user")


def test_upload_video_gs_uri(mock_client):
    mock_client.upload.return_value = {"video_id": "vid_gs", "status": "uploaded"}
    from nomadicml_mcp.server import upload_video
    result = upload_video("gs://my-bucket/video.mp4")
    assert result["video_id"] == "vid_gs"


def test_upload_video_local_not_found(mock_client):
    from nomadicml_mcp.server import upload_video
    with pytest.raises(FileNotFoundError):
        upload_video("/nonexistent/video.mp4")


def test_upload_video_with_name_and_folder(mock_client):
    mock_client.upload.return_value = {"video_id": "vid_xyz", "status": "uploaded"}
    from nomadicml_mcp.server import upload_video
    result = upload_video("https://example.com/v.mp4", name="My Video", folder="my_folder", scope="org")
    mock_client.upload.assert_called_once_with(
        "https://example.com/v.mp4", name="My Video", folder="my_folder", scope="org"
    )


# ---------------------------------------------------------------------------
# upload_videos_batch
# ---------------------------------------------------------------------------

def test_upload_videos_batch(mock_client):
    mock_client.upload.return_value = [
        {"video_id": "vid_1", "status": "uploaded"},
        {"video_id": "vid_2", "status": "uploaded"},
    ]
    from nomadicml_mcp.server import upload_videos_batch
    result = upload_videos_batch(["https://a.com/1.mp4", "https://b.com/2.mp4"])
    assert result["uploaded"] == 2
    assert len(result["videos"]) == 2


# ---------------------------------------------------------------------------
# analyze_video
# ---------------------------------------------------------------------------

def test_analyze_video_ask(mock_client):
    mock_client.analyze.return_value = {
        "video_id": "vid_abc", "mode": "rapid_review",
        "status": "completed", "events": [],
    }
    from nomadicml_mcp.server import analyze_video
    result = analyze_video("vid_abc", "ASK", custom_prompt="Find near misses")
    assert result["status"] == "completed"
    # SDK called with single video_id string (not list) and wait_for_completion=True
    call_args = mock_client.analyze.call_args
    assert call_args.args[0] == "vid_abc"
    assert call_args.kwargs["wait_for_completion"] is True
    # custom_category must be passed for ASK
    assert "custom_category" in call_args.kwargs


def test_analyze_video_agent_no_custom_category(mock_client):
    """DRIVING_VIOLATIONS and other agent types must NOT receive custom_category."""
    mock_client.analyze.return_value = {
        "video_id": "vid_abc", "mode": "agent",
        "status": "completed", "events": [],
    }
    from nomadicml_mcp.server import analyze_video
    analyze_video("vid_abc", "DRIVING_VIOLATIONS")
    assert "custom_category" not in mock_client.analyze.call_args.kwargs


def test_analyze_video_invalid_type(mock_client):
    from nomadicml_mcp.server import analyze_video
    with pytest.raises(ValueError, match="Invalid analysis_type"):
        analyze_video("vid_abc", "FAKE_TYPE")


def test_analyze_video_invalid_category_only_for_ask(mock_client):
    """Category validation only fires for ASK; other types ignore the category param."""
    from nomadicml_mcp.server import analyze_video
    with pytest.raises(ValueError, match="Invalid category"):
        analyze_video("vid_abc", "ASK", custom_prompt="test", category="FAKE")


def test_analyze_video_no_wait(mock_client):
    mock_client.analyze.return_value = {
        "batch_metadata": {"batch_id": "batch_789"},
        "results": [{"video_id": "vid_abc", "status": "started"}],
    }
    from nomadicml_mcp.server import analyze_video
    result = analyze_video("vid_abc", "LANE_CHANGE", wait=False)
    assert result["status"] == "started"
    assert result["batch_id"] == "batch_789"
    # For wait=False, SDK is called with a list and wait_for_completion=False
    call_args = mock_client.analyze.call_args
    assert call_args.args[0] == ["vid_abc"]
    assert call_args.kwargs["wait_for_completion"] is False


def test_analyze_video_timeout(mock_client):
    mock_client.analyze.return_value = {
        "video_id": "vid_abc", "mode": "agent",
        "status": "completed", "events": [],
    }
    from nomadicml_mcp.server import analyze_video
    # SDK returns immediately with completed status — no polling needed
    result = analyze_video("vid_abc", "LANE_CHANGE", timeout_seconds=1)
    assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# analyze_folder
# ---------------------------------------------------------------------------

def test_analyze_folder(mock_client):
    mock_client.analyze.return_value = {"results": [], "batch_metadata": {}}
    from nomadicml_mcp.server import analyze_folder
    result = analyze_folder("my_folder", "DRIVING_VIOLATIONS")
    mock_client.analyze.assert_called_once()
    call_kwargs = mock_client.analyze.call_args.kwargs
    assert call_kwargs["folder"] == "my_folder"


# ---------------------------------------------------------------------------
# get_batch_analysis
# ---------------------------------------------------------------------------

def test_get_analysis(mock_client):
    mock_client.get_batch_analysis.return_value = {
        "batch_metadata": {"batch_id": "batch_123"},
        "results": [{"status": "completed", "events": []}],
    }
    from nomadicml_mcp.server import get_analysis
    result = get_analysis("batch_123", wait=False)
    mock_client.get_batch_analysis.assert_called_once_with("batch_123")


def test_get_batch_analysis(mock_client):
    mock_client.get_batch_analysis.return_value = {"batch_metadata": {}, "results": []}
    from nomadicml_mcp.server import get_batch_analysis
    get_batch_analysis("batch_123")
    mock_client.get_batch_analysis.assert_called_once_with("batch_123")


def test_get_batch_analysis_with_filter(mock_client):
    mock_client.get_batch_analysis.return_value = {"batch_metadata": {}, "results": []}
    from nomadicml_mcp.server import get_batch_analysis
    get_batch_analysis("batch_123", filter_status="approved")
    mock_client.get_batch_analysis.assert_called_once_with("batch_123", filter="approved")


def test_get_batch_analysis_invalid_filter(mock_client):
    from nomadicml_mcp.server import get_batch_analysis
    with pytest.raises(ValueError, match="Invalid filter_status"):
        get_batch_analysis("batch_123", filter_status="nonsense")


# ---------------------------------------------------------------------------
# thumbnails
# ---------------------------------------------------------------------------

def test_get_visuals(mock_client):
    mock_client.get_visuals.return_value = ["https://url1.jpg", "https://url2.jpg"]
    from nomadicml_mcp.server import get_visuals
    result = get_visuals("vid_abc", "analysis_xyz")
    assert len(result) == 2


def test_get_visual(mock_client):
    mock_client.get_visual.return_value = "https://url0.jpg"
    from nomadicml_mcp.server import get_visual
    result = get_visual("vid_abc", "analysis_xyz", 0)
    assert result == "https://url0.jpg"


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def test_search_videos(mock_client):
    mock_client.search.return_value = {"summary": "Found 3 matches", "thoughts": [], "matches": []}
    from nomadicml_mcp.server import search_videos
    result = search_videos("near misses at crosswalks", "fleet_folder")
    mock_client.search.assert_called_once_with(
        query="near misses at crosswalks", folder_name="fleet_folder", scope="user"
    )


# ---------------------------------------------------------------------------
# folder management
# ---------------------------------------------------------------------------

def test_create_folder(mock_client):
    mock_client.create_folder.return_value = {"id": "f1", "name": "test"}
    from nomadicml_mcp.server import create_folder
    create_folder("test", scope="org", description="My folder")
    mock_client.create_folder.assert_called_once_with("test", scope="org", description="My folder")


def test_get_or_create_folder(mock_client):
    mock_client.create_or_get_folder.return_value = {"id": "f2", "name": "test"}
    from nomadicml_mcp.server import get_or_create_folder
    get_or_create_folder("test")
    mock_client.create_or_get_folder.assert_called_once()


def test_get_folder(mock_client):
    mock_client.get_folder.return_value = {"id": "f3", "name": "test", "video_count": 5}
    from nomadicml_mcp.server import get_folder
    result = get_folder("test")
    assert result["video_count"] == 5


# ---------------------------------------------------------------------------
# video management
# ---------------------------------------------------------------------------

def test_list_videos(mock_client):
    mock_client.my_videos.return_value = [{"video_id": "v1"}, {"video_id": "v2"}]
    from nomadicml_mcp.server import list_videos
    result = list_videos(folder="my_folder")
    assert len(result) == 2


def test_delete_video(mock_client):
    mock_client.delete_video.return_value = {"status": "deleted"}
    from nomadicml_mcp.server import delete_video
    result = delete_video("vid_abc")
    mock_client.delete_video.assert_called_once_with("vid_abc")


# ---------------------------------------------------------------------------
# structured ODD
# ---------------------------------------------------------------------------

def test_generate_structured_odd_default(mock_client):
    mock_client.generate_structured_odd.return_value = {"csv": "col1,col2\n", "share_url": None}
    from nomadicml_mcp.server import generate_structured_odd
    result = generate_structured_odd("vid_abc")
    assert "csv" in result


def test_generate_structured_odd_custom_columns(mock_client):
    mock_client.generate_structured_odd.return_value = {"csv": "a,b\n"}
    from nomadicml_mcp.server import generate_structured_odd
    cols = json.dumps([{"name": "road_type", "prompt": "Type of road", "type": "categorical",
                        "literals": ["urban", "rural"]}])
    result = generate_structured_odd("vid_abc", use_default_columns=False, custom_columns_json=cols)
    assert "csv" in result


def test_generate_structured_odd_bad_json(mock_client):
    from nomadicml_mcp.server import generate_structured_odd
    with pytest.raises(ValueError, match="not valid JSON"):
        generate_structured_odd("vid_abc", use_default_columns=False, custom_columns_json="{bad json}")


# ---------------------------------------------------------------------------
# cloud integrations
# ---------------------------------------------------------------------------

def test_list_cloud_integrations(mock_client):
    mock_client.cloud_integrations.list.return_value = []
    from nomadicml_mcp.server import list_cloud_integrations
    list_cloud_integrations()
    mock_client.cloud_integrations.list.assert_called_once_with()


def test_list_cloud_integrations_filter(mock_client):
    mock_client.cloud_integrations.list.return_value = []
    from nomadicml_mcp.server import list_cloud_integrations
    list_cloud_integrations(provider="gcs")
    mock_client.cloud_integrations.list.assert_called_once_with(type="gcs")


def test_list_cloud_integrations_invalid_provider(mock_client):
    from nomadicml_mcp.server import list_cloud_integrations
    with pytest.raises(ValueError):
        list_cloud_integrations(provider="azure")


def test_add_gcs_integration_missing_file(mock_client):
    from nomadicml_mcp.server import add_gcs_integration
    with pytest.raises(FileNotFoundError):
        add_gcs_integration("My GCS", "my-bucket", "/nonexistent/creds.json")


def test_add_s3_integration(mock_client):
    mock_client.cloud_integrations.add.return_value = {"id": "integ_s3"}
    from nomadicml_mcp.server import add_s3_integration
    result = add_s3_integration(
        name="AWS archive", bucket="my-bucket",
        access_key_id="AKID", secret_access_key="SECRET", region="us-east-1"
    )
    mock_client.cloud_integrations.add.assert_called_once()


def test_upload_from_cloud_invalid_uri(mock_client):
    from nomadicml_mcp.server import upload_from_cloud
    with pytest.raises(ValueError, match="gs://"):
        upload_from_cloud(["https://not-a-cloud-uri.com/video.mp4"])


def test_upload_from_cloud(mock_client):
    mock_client.upload.return_value = [{"video_id": "vid_gs1", "status": "uploaded"}]
    from nomadicml_mcp.server import upload_from_cloud
    result = upload_from_cloud(["gs://bucket/video.mp4"])
    assert result["imported"] == 1


# ---------------------------------------------------------------------------
# missing API key
# ---------------------------------------------------------------------------

def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("NOMADICML_API_KEY", raising=False)
    from nomadicml_mcp.server import get_client
    with pytest.raises(ValueError, match="NOMADICML_API_KEY"):
        get_client()
