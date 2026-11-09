import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from api.experimental_notetaker import ExperimentalNotetaker

pytestmark = pytest.mark.django_db


@pytest.fixture
def notes_dir(settings, tmp_path):
    settings.COVER_EXPERIMENT_NOTETAKER_ENABLED = True
    settings.COVER_EXPERIMENT_NOTES_DIR = tmp_path / "notes"
    return settings.COVER_EXPERIMENT_NOTES_DIR


def test_saves_json_and_receipt(api_client_with_token_credentials, notes_dir):
    client, user = api_client_with_token_credentials
    blob = {
        "outcome": "match",
        "search_hash": "0" * 16,
        "rank": 1,
        "arbitrary": {"unicode": "café", "values": [None, True, 3]},
        "performance": {"hashes_checked": 2299, "database_match_ms": 2.1},
    }
    response = client.post(reverse("api:experimental-notetaker"), blob, format="json")
    assert response.status_code == 201
    files = list(notes_dir.glob("*.json"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert record["payload"] == blob
    assert record["user_id"] == user.pk
    assert record["id"] == response.data["id"]
    assert record["received_at"] == response.data["received_at"]
    assert list(notes_dir.glob("*.tmp")) == []


def test_no_match_payload_is_retained(api_client_with_credentials, notes_dir):
    payload = {
        "outcome": "no_match",
        "selected_comic": None,
        "rank": None,
        "results": [{"id": 42, "distance": 8}],
    }
    assert (
        api_client_with_credentials.post(
            reverse("api:experimental-notetaker"), payload, format="json"
        ).status_code
        == 201
    )
    assert json.loads(next(notes_dir.glob("*.json")).read_text())["payload"] == payload


def test_authentication_and_disable(api_client, api_client_with_credentials, notes_dir, settings):
    url = reverse("api:experimental-notetaker")
    assert APIClient().post(url, {}, format="json").status_code == 401
    settings.COVER_EXPERIMENT_NOTETAKER_ENABLED = False
    assert api_client_with_credentials.post(url, {}, format="json").status_code == 404
    assert not notes_dir.exists()


def test_rejects_bad_json_and_oversize(api_client_with_credentials, notes_dir):
    client = api_client_with_credentials
    url = reverse("api:experimental-notetaker")
    assert client.post(url, "{", content_type="application/json").status_code == 400
    assert client.post(url, [1], format="json").status_code == 400
    assert client.post(url, {"large": "x" * 65536}, format="json").status_code == 400
    assert client.post(url, '{"number":1e1000}', content_type="application/json").status_code == 400
    assert not notes_dir.exists()


def test_storage_failure_is_not_success(api_client_with_credentials, notes_dir):
    with patch("api.experimental_notetaker.os.open", side_effect=OSError("unavailable")):
        response = api_client_with_credentials.post(
            reverse("api:experimental-notetaker"), {"test": True}, format="json"
        )
    assert response.status_code == 503
    assert list(notes_dir.glob("*.json")) == []


def test_concurrent_records_do_not_overwrite(notes_dir):
    # No live database connection is used by the file writer in these threads.
    user = SimpleNamespace(pk=999, is_authenticated=True)
    view = ExperimentalNotetaker.as_view()

    def write(index):
        request = APIRequestFactory().post("/", {"index": index}, format="json")
        force_authenticate(request, user=user)
        return view(request).status_code

    # Disable throttles directly on the temporary view without global settings races.
    with (
        patch.object(ExperimentalNotetaker, "throttle_classes", []),
        ThreadPoolExecutor(max_workers=4) as pool,
    ):
        assert list(pool.map(write, range(12))) == [201] * 12
    assert len(list(notes_dir.glob("*.json"))) == 12
    assert {json.loads(p.read_text())["payload"]["index"] for p in notes_dir.glob("*.json")} == set(
        range(12)
    )
