"""Exact nearest-cover search using PostgreSQL's native XOR and popcount.

All hashes remain inside PostgreSQL; only eight winners cross the wire. Stored
generated integers avoid parsing hex for every request and stay correct on bulk
updates. A bounded top-N sort follows a per-issue minimum, so many variants cannot
crowd other comics out. No approximate index can silently omit the nearest comic.
"""

from django.conf import settings
from django.db import connection
from rest_framework import serializers

from api.cover_search_diagnostics import execute_matching
from api.v1_0.serializers.issue import IssueListSerializer

MATCH_SQL = """
input AS (SELECT CAST(%s AS bigint) AS target),
candidates AS (
    SELECT id AS issue_id, bit_count((cover_hash_int # input.target)::bit(64)) AS distance
    FROM comicsdb_issue CROSS JOIN input WHERE cover_hash_int IS NOT NULL
    UNION ALL
    SELECT issue_id, bit_count((cover_hash_int # input.target)::bit(64)) AS distance
    FROM comicsdb_variant CROSS JOIN input WHERE cover_hash_int IS NOT NULL
),
ranked AS MATERIALIZED (
    SELECT issue_id, min(distance) AS distance FROM candidates
    GROUP BY issue_id ORDER BY distance, issue_id LIMIT 8
)
SELECT r.issue_id, r.distance, c.variant_id, c.image, c.hash
FROM ranked r CROSS JOIN input CROSS JOIN LATERAL (
    SELECT * FROM (
        SELECT NULL::bigint AS variant_id, image, cover_hash AS hash,
               bit_count((cover_hash_int # input.target)::bit(64)) AS distance
        FROM comicsdb_issue WHERE id = r.issue_id AND cover_hash_int IS NOT NULL
        UNION ALL
        SELECT id, image, cover_hash,
               bit_count((cover_hash_int # input.target)::bit(64)) AS distance
        FROM comicsdb_variant WHERE issue_id = r.issue_id AND cover_hash_int IS NOT NULL
    ) covers ORDER BY distance, variant_id NULLS FIRST LIMIT 1
) c ORDER BY r.distance, r.issue_id
"""


class CoverSearchInput(serializers.Serializer):
    cover_hash = serializers.RegexField(r"\A[0-9a-fA-F]{16}\Z", trim_whitespace=False)


class MatchedCoverSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(allow_null=True)
    image = serializers.URLField(allow_null=True)
    cover_hash = serializers.CharField()


class CoverSearchIssueSerializer(IssueListSerializer):
    distance = serializers.IntegerField(min_value=0, max_value=64)
    matched_cover = MatchedCoverSerializer()

    class Meta(IssueListSerializer.Meta):
        fields = (*IssueListSerializer.Meta.fields, "distance", "matched_cover")


class CoverSearchDiagnosticsSerializer(serializers.Serializer):
    database_match_ms = serializers.FloatField(min_value=0)
    hashes_checked = serializers.IntegerField(min_value=0)


class CoverSearchResponseSerializer(serializers.Serializer):
    cover_hash = serializers.CharField()
    count = serializers.IntegerField(min_value=0, max_value=8)
    results = CoverSearchIssueSerializer(many=True)
    diagnostics = CoverSearchDiagnosticsSerializer(required=False)


def closest_covers(cover_hash):
    value = int(cover_hash, 16)
    if value >= 2**63:
        value -= 2**64
    with connection.cursor() as cursor:
        rows, diagnostics = execute_matching(
            cursor,
            MATCH_SQL,
            [value],
            enabled=getattr(settings, "COVER_SEARCH_DIAGNOSTICS", False),
        )
    return rows, diagnostics
