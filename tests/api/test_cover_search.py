import random
from datetime import date
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from PIL import Image

from api.cover_search import closest_covers
from comicsdb.models import Issue, Publisher, Rating, Series, Variant

pytestmark = pytest.mark.django_db


@pytest.fixture
def corpus(single_issue_type):
    publisher = Publisher.objects.create(name="Hash fixtures")
    series = Series.objects.create(
        name="Hash fixtures",
        sort_name="Hash fixtures",
        volume=1,
        year_began=2026,
        publisher=publisher,
        series_type=single_issue_type,
    )
    Rating.objects.get_or_create(pk=1, defaults={"name": "Unknown"})
    issues = [
        Issue.objects.create(series=series, number=str(i), cover_date=date(2026, 1, 1))
        for i in range(12)
    ]
    for i, issue in enumerate(issues):
        Issue.objects.filter(pk=issue.pk).update(cover_hash=f"{(1 << i) - 1:016x}")
    return issues


def test_exact_order_and_limit(corpus, api_client_with_token_credentials, settings):
    settings.COVER_SEARCH_DIAGNOSTICS = True
    client, _ = api_client_with_token_credentials
    response = client.get(reverse("api:issue-cover-search"), {"cover_hash": "0000000000000000"})
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert [r["id"] for r in response.data["results"]] == [i.pk for i in corpus[:8]]
    assert [r["distance"] for r in response.data["results"]] == list(range(8))
    assert response.data["diagnostics"]["database_match_ms"] >= 0
    assert response.data["diagnostics"]["hashes_checked"] == len(corpus)
    assert "series" in response.data["results"][0]


def test_variant_minimum_deduplicates_and_breaks_ties(corpus, settings):
    settings.COVER_SEARCH_DIAGNOSTICS = False
    variants = [Variant.objects.create(issue=corpus[-1], image="") for _ in range(10)]
    Variant.objects.filter(pk__in=[v.pk for v in variants]).update(cover_hash="0000000000000000")
    rows, elapsed = closest_covers("0000000000000000")
    assert elapsed is None
    assert len({row[0] for row in rows}) == 8
    assert rows[0][0] == corpus[0].pk
    assert rows[1][:3] == (corpus[-1].pk, 0, variants[0].pk)


@pytest.mark.parametrize(
    "value", ["", "0" * 15, "0" * 17, "g" * 16, " 0000000000000000", "0000000000000000\n"]
)
def test_rejects_bad_hash(value, api_client_with_credentials):
    assert (
        api_client_with_credentials.get(
            reverse("api:issue-cover-search"), {"cover_hash": value}
        ).status_code
        == 400
    )


def test_requires_authentication(api_client):
    assert (
        api_client.get(reverse("api:issue-cover-search"), {"cover_hash": "0" * 16}).status_code
        == 401
    )


def test_generated_value_handles_bulk_updates_and_invalid_hashes(corpus):
    Issue.objects.filter(pk=corpus[0].pk).update(cover_hash="FFFFFFFFFFFFFFFF")
    corpus[0].refresh_from_db()
    assert corpus[0].cover_hash_int == -1
    Issue.objects.filter(pk=corpus[0].pk).update(cover_hash="not-a-hash")
    corpus[0].refresh_from_db()
    assert corpus[0].cover_hash_int is None
    assert corpus[0].pk not in [r[0] for r in closest_covers("ffffffffffffffff")[0]]


def test_empty_corpus_with_and_without_diagnostics(settings):
    for enabled in [True, False]:
        settings.COVER_SEARCH_DIAGNOSTICS = enabled
        rows, ms = closest_covers("ffffffffffffffff")
        assert rows == []
        assert ms is None if not enabled else ms["database_match_ms"] >= 0


def test_variant_hash_lifecycle_and_backfill(corpus, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    output = BytesIO()
    Image.new("RGB", (40, 60), "white").save(output, "PNG")
    v = Variant.objects.create(
        issue=corpus[0], image=SimpleUploadedFile("white.png", output.getvalue())
    )
    v.refresh_from_db()
    assert v.cover_hash == "8000000000000000"
    assert v.cover_hash_int == -(2**63)
    Variant.objects.filter(pk=v.pk).update(cover_hash="")
    call_command("backfill_variant_hashes")
    v.refresh_from_db()
    assert v.cover_hash == "8000000000000000"
    v.image = ""
    v.save()
    v.refresh_from_db()
    assert v.cover_hash == ""
    assert v.cover_hash_int is None


def test_sql_ranking_matches_brute_force(corpus, settings):
    rng = random.Random(381)  # noqa: S311 - deterministic test data, not credentials
    hashes = {}
    for issue in corpus:
        value = rng.getrandbits(64)
        hashes[issue.pk] = [value]
        Issue.objects.filter(pk=issue.pk).update(cover_hash=f"{value:016x}")
        for _ in range(3):
            value = rng.getrandbits(64)
            variant = Variant.objects.create(issue=issue, image="")
            Variant.objects.filter(pk=variant.pk).update(cover_hash=f"{value:016x}")
            hashes[issue.pk].append(value)
    for enabled in [True, False]:
        settings.COVER_SEARCH_DIAGNOSTICS = enabled
        for query in [0, 2**63, 2**64 - 1, rng.getrandbits(64)]:
            expected = sorted(
                (min((h ^ query).bit_count() for h in values), pk) for pk, values in hashes.items()
            )[:8]
            rows, _ = closest_covers(f"{query:016x}")
            assert [(r[1], r[0]) for r in rows] == expected


def test_diagnostic_count_includes_all_variants_and_excludes_invalid(corpus, settings):
    settings.COVER_SEARCH_DIAGNOSTICS = True
    variant = Variant.objects.create(issue=corpus[0], image="")
    Variant.objects.filter(pk=variant.pk).update(cover_hash="ffffffffffffffff")
    Issue.objects.filter(pk=corpus[-1].pk).update(cover_hash="invalid")
    _, diagnostics = closest_covers("0000000000000000")
    assert diagnostics["hashes_checked"] == len(corpus)


def test_source_only_cover_retains_hash_and_returns_remote_url(corpus, api_client_with_credentials):
    issue = corpus[0]
    source = "https://static.metron.cloud/media/issue/2026/11/09/remote.jpg"
    Issue.objects.filter(pk=issue.pk).update(
        cover_source_url=source, cover_hash="8000000000000000", image=""
    )
    issue.refresh_from_db()
    issue.desc = "Metadata-only update"
    issue.save()
    issue.refresh_from_db()
    assert issue.cover_hash == "8000000000000000"
    assert not issue.image
    response = api_client_with_credentials.get(
        reverse("api:issue-cover-search"), {"cover_hash": issue.cover_hash}
    )
    assert response.status_code == 200
    row = next(r for r in response.data["results"] if r["id"] == issue.pk)
    assert row["image"] == source
    assert row["matched_cover"]["image"] == source
    assert row["distance"] == 0
    response = api_client_with_credentials.get(reverse("api:issue-detail", kwargs={"pk": issue.pk}))
    assert response.data["image"] == source
