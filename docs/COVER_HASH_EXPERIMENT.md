# Cover perceptual hash experiment

Branch: `codex/perceptual-hash-experiments`. The Android project is [../android](../android); its application ID is `cloud.metron.cphtest` and its label is CPHTest.

## API contract

`GET /api/issue/cover-search/?cover_hash=0123456789abcdef`

Authenticate with the usual `Authorization: Bearer <Metron API key>`. Input is exactly 16 hexadecimal characters (upper- or lowercase); whitespace, truncated hashes, and extra characters return 400. Authentication and existing API throttles apply. GET is read-only and responses are not cached.

The response is an object containing `cover_hash`, `count` (0–8), and `results`. Each result has the normal issue-list/text-search fields plus:

- `distance`: Hamming distance, 0–64; lower is closer. Zero means identical hashes, not proof of identical artwork.
- `matched_cover`: `variant_id` (null for the standard cover), `image` (absolute URL), and `cover_hash` for the winning cover. The original top-level `image` and `cover_hash` continue to describe the standard cover.

Results contain up to eight distinct issues, in ascending distance and then issue ID. Each comic is ranked by its closest standard or variant cover. A tie between covers of one comic prefers its standard cover, then the lowest variant ID. Fewer than eight searchable comics returns all of them; an empty corpus returns `results: []`. There is no confidence threshold or pagination.

## Matching and performance

A stored generated bigint converts each valid 64-bit hexadecimal hash once when the hash changes, including bulk SQL updates. Blank or malformed hashes produce NULL and are excluded. PostgreSQL performs native integer XOR and `bit_count` over 64 bits, aggregates each issue's minimum, and applies a top-eight sort. It does not transfer the catalog to Python or perform one query per candidate. A second bounded query obtains issue/series metadata for the eight winners.

This is an exact scan, O(number of hashed covers), with no extension or approximate-neighbor recall tradeoff. A conventional B-tree does not order Hamming neighbors, so no misleading index is added. Measure against production-size data before drawing scaling conclusions.

With `COVER_SEARCH_DIAGNOSTICS=True` (the branch default), the response includes:

```json
"diagnostics": { "database_match_ms": 2.137 }
```

This is PostgreSQL wall-clock time from before scanning candidate hashes through producing the eight match records. It excludes planning, authentication, network transport, and Django's issue serialization. The measurement executes the matching query once; it does not replay the search with EXPLAIN. CPHTest also displays client image/hash and API round-trip times separately.

All timing instrumentation is grouped in `api/cover_search_diagnostics.py`. Set `COVER_SEARCH_DIAGNOSTICS=False` to remove the clock wrapper and diagnostic response member while retaining identical rankings. If this graduates to production, remove that helper and replace its call site with a direct cursor execution; the matching SQL has no instrumentation dependency. Do not compare a cold first request to warm requests without labeling them.

## Existing and new variants

The migration adds `Variant.cover_hash` and generated integer columns to Issue and Variant. Existing main hashes are converted automatically. Existing variant images need the explicit resumable backfill:

```sh
python manage.py migrate
python manage.py backfill_variant_hashes
```

Backfill reads configured media storage (including S3); it never downloads images inside a schema migration. Missing/unreadable images are reported, completed hashes are retained, and rerunning processes only missing hashes. Newly saved or replaced variant images are hashed automatically. Direct/bulk variant image writes must clear/recompute their hash explicitly, since they bypass model save hooks. Database-generated integers still update automatically when either model's hash changes.

## Local testing

Start local Metron with its existing PowerShell helper. The local development database and the previously imported catalog remain in place; no remote catalog is modified.

```powershell
& ./.work/metron-local/metron-local.ps1 start
& ./.work/metron-local/metron-local.ps1 manage migrate
& ./.work/metron-local/metron-local.ps1 manage backfill_variant_hashes
```

The helper uses `--noreload`; restart the web process after code changes. Use an API token issued by **local Metron**. Cerebro's upstream token will not authenticate to this separate local database. A prepared local configuration is stored in the ignored `.work/metron-local/cphtest-connection.json`; copy its API key into CPHTest rather than committing it.

For an Android Studio emulator, configure `http://10.0.2.2:8000`. For a USB-connected physical device, Android Studio's terminal can forward the device port without exposing Django on your LAN:

```sh
adb reverse tcp:8000 tcp:8000
```

Then configure CPHTest with `http://127.0.0.1:8000`. Remove that forwarding later with `adb reverse --remove tcp:8000`. A LAN hostname also works if you deliberately bind the development server to that interface, allow the hostname in Django, and configure the host firewall.

## Validation

Endpoint tests cover authentication, input rejection, exact and randomized brute-force ordering, signed 64-bit values, malformed stored hashes, duplicate variants, empty data, diagnostics on/off, and variant hashing/backfill. Existing issue API, model, and response-cache tests provide regression coverage.

Android tests use deterministic RGB fixtures generated by Python ImageHash and Pillow 13.0.0. They cover both resize pass orders, upscaling, downscaling, uniform images, and 64-bit hex formatting, plus HTTP authorization, redirect refusal, and address normalization. The scanner's physical camera/corner editor and first-use Google Play services download require a compatible test device.

See [server container update instructions](../DEPLOYMENT.md#updating-the-cover-hash-experiment) before updating a running server. No remote deployment is performed by this experiment setup.
