# ruff: noqa: S608
"""Removable experiment instrumentation; no EXPLAIN or duplicate search execution.

The database clock measures execution of matching and its small result projection.
It excludes planning, transport, authentication, and Django serialization. Disable
with COVER_SEARCH_DIAGNOSTICS=False; deleting this module and its call site later
does not change the ranking query or the result schema.
"""


def execute_matching(cursor, sql, params, *, enabled):
    if not enabled:
        cursor.execute("WITH " + sql, params)
        return cursor.fetchall(), None
    clock = "experimental_clock AS MATERIALIZED (SELECT clock_timestamp() AS started), "
    # A dependency in each candidate scan starts the clock before any hashes are read.
    sql = sql.replace(
        "WHERE cover_hash_int IS NOT NULL",
        "WHERE cover_hash_int IS NOT NULL AND (SELECT started FROM experimental_clock) IS NOT NULL",
    )
    # Count cover rows in the existing aggregation, without another catalog scan.
    sql = sql.replace(
        "SELECT issue_id, min(distance) AS distance FROM candidates",
        "SELECT issue_id, min(distance) AS distance, "
        "sum(count(*)) OVER () AS hashes_checked FROM candidates",
    ).replace("SELECT r.issue_id, r.distance,", "SELECT r.hashes_checked, r.issue_id, r.distance,")
    # Only trusted static SQL is composed here; the input hash stays parameterized.
    cursor.execute(
        "WITH " + clock + "experimental_matches AS MATERIALIZED (WITH " + sql + ") "
        "SELECT COALESCE(json_agg(m ORDER BY m.distance, m.issue_id) "
        "FILTER (WHERE m.issue_id IS NOT NULL), '[]'::json), "
        "EXTRACT(EPOCH FROM (clock_timestamp() - c.started)) * 1000 "
        "FROM experimental_clock c LEFT JOIN experimental_matches m ON TRUE "
        "GROUP BY c.started",
        params,
    )
    matches, elapsed = cursor.fetchone()
    return [
        tuple(m[k] for k in ("issue_id", "distance", "variant_id", "image", "hash"))
        for m in matches
    ], {
        "database_match_ms": round(float(elapsed), 3),
        "hashes_checked": int(matches[0]["hashes_checked"]) if matches else 0,
    }
