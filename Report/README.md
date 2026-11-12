# Perceptual Hash Experiment Report

Open [the report](perceptual-hash-experiment-report.html) in a web browser. It embeds the charts and photographs; standalone copies and the source data are retained alongside it.

This archive is intentionally committed only to the experimental branch at Eric’s request. It must not be included in an upstream submission. The unrelated private collection snapshot and runtime caches are omitted.

Regenerate with `python Report/analyze.py` from the repository root after installing matplotlib and numpy. The generator reads the archived `Report/raw/` notes and does not start Metron or PostgreSQL or use API credentials.

# CPHTest Scan Analysis — November 11, 2026

Local Metron and PostgreSQL were stopped before extraction and remain stopped.
The archive contains 169 original notes from November 11, 16:03:30–17:21:13 EST.
The previously deleted November 9 test note is not included.

## Policy-adjusted Comic Outcomes

- Comic trials reconstructed: 138
- First-scan successes: 109 (78.99%)
- Additional successes on second scan: 18 (13.04%)
- Cumulative successes within two scans: 127 (92.03%)
- Failures after both attempts: 11 (7.97%)
- Retried comics: 29; retry rescued 18 (62.1%).

167 included attempts = 109 single-attempt trials + 29 two-attempt trials.
The raw archive retains 169 notes; trial 7 and its two attempts are excluded from results.
40 included no-match attempts = 29 first failures + 11 failed retries.
Rank frequencies count each comic once, using its eventual successful rank or one final failure.
Final ranks: #1 = 122, #2 = 3, #3 = 2, #4–8 = 0, final failure = 11.
Rank #1 was 96.06% of successful comics and 88.41% of all trials.
Competition ranking honors ties (e.g. 1, 1, 3).

## Methodology

See methodology.html for the full tester-supplied methodology and captioned workflow/environment images, also embedded in perceptual-hash-experiment-report.html. Editorial corrections clarify the app name, bit distances, sample count, and perspective-correction sequence. The reported 21% compares issue counts rather than asserting a verified fraction of upstream cover hashes.

## Pairing Assumptions and Limitations

Trials are reconstructed from chronological records and the stated policy. Failure notes contain no intended comic/session ID. Later user confirmations identify 9 included failed comics; 2 remain unidentified. Assumes every attempt was recorded and the policy was followed without exceptions.
Of the 11 included failed trials, 9 titles were subsequently confirmed by the user; 2 remain unknown. Confirmed identities are stored separately from the raw notes. No unconfirmed sequence guesses are treated as known identities.
The full audit contains all 30 inferred retry pairs, including the excluded trial; the results contain 29 eligible pairs, their source record IDs, timestamps, and hash changes.
One pair (attempts 38–39, Monstress #55) changed by 20 hash bits; this is a review flag,
not evidence of a policy violation. No pair was excluded or regrouped using a hash threshold.

Every successful selected rank, array position, and bit distance validated against its result list.
There were no repeated event IDs or repeated selected issue IDs. All 169 records searched 40,112 hashes.
This is a descriptive analysis of one session, not a randomized accuracy estimate.

## Timing Interpretation

All per-attempt statistics include the 167 eligible attempts, including failed first scans and failed retries; trial 7’s two attempts are excluded.
Postgres hash search is included in API round trip. Do not add those two measurements together.
User experience is the sum of Android client hash processing and API round trip; it excludes camera/corner editing,
user decision time, feedback submission time, and artwork loading. It is not full scan wall-clock latency.
`processing-work-per-comic.csv` sums the one or two measured attempts belonging to each inferred trial.
No timing outliers, first requests, or presumed cold/warm samples were removed; the sole trial exclusion is recorded in excluded-trials.json.

## Files

- `raw/`: byte-for-byte original notes, preserved independently of source records.
- `checksums.json`: SHA-256 checksums and byte sizes for the original notes.
- `raw-notes.jsonl`: combined chronological raw records.
- `attempts.csv`: included attempts, with original inferred trial/attempt ordinal.
- `all-attempts-audit.csv`, `all-comic-trials-audit.csv`, `all-retry-pairs-audit.csv`: full records with inclusion flags.
- `excluded-trials.json`: user-requested coverage exclusion and rationale.
- `comic-trials.csv`: one outcome per inferred comic trial.
- `retry-pair-audit.csv`: pairing audit and hash changes.
- `outcomes.csv`, `rank-frequency.csv`: chart data.
- `processing-times-per-attempt.csv`, `processing-work-per-comic.csv`: timing summaries.
- `summary.json`: machine-readable findings and limitations.
- PNG/SVG/PDF charts, self-contained `perceptual-hash-experiment-report.html`, and this reproducible script.

## Appendix: Measurement Definitions

These are elapsed wall-clock measurements, not CPU-only measurements. Waiting,
I/O, scheduling delays, and garbage collection inside a measurement window are
included. The processing order is:

Android client hash processing → API request → Postgres hash search → API response.
API round trip surrounds the request, database work, and response.

### Android Client Hash Processing

Starts on Android immediately before dispatching hash work to `Dispatchers.Default`.
Ends immediately after the hexadecimal hash string is produced, before bitmap
recycling and returning the finished result to the UI thread.

Includes waiting for the background task to start; reading the corrected JPEG's
dimensions; reading and decoding the JPEG into an ARGB bitmap; allocating/copying
the pixel array; converting to grayscale; Lanczos resizing to 32 × 32; computing
the DCT; selecting the 8 × 8 coefficients; calculating the median; and forming
the 64-bit hexadecimal hash. First-use hash-object initialization, if any, is
inside this window as well.

Excludes camera capture, corner adjustment, perspective correction, preview,
user confirmation, bitmap recycling after the timestamp, and dispatch back to
the UI thread after the hash completes.

### Postgres Hash Search

Starts when PostgreSQL evaluates the materialized start-clock expression before
scanning candidate hashes. Ends when the outer SQL result samples the elapsed
clock after ranking and assembling the match records. This is the instrumented
matching portion of query execution, not the complete database request duration.

Includes reading valid issue and variant hashes; XOR/popcount Hamming distance
calculations; taking each comic's closest cover; ranking and selecting the top
eight distinct comics; retrieving winning cover hashes, URLs, and variant IDs;
counting hashes checked; SQL result assembly; and instrumentation overhead.

Excludes SQL parsing/planning, opening a database connection, transport between
Django and PostgreSQL, authentication, the subsequent query for descriptive
metadata of the eight comics, and Django's response serialization.

### API Round Trip

Starts immediately before dispatching the API operation to `Dispatchers.IO`.
Ends after it returns to the UI thread.

Includes client dispatch/queue waits; constructing and validating the request and
headers; acquiring a connection; DNS, TCP setup, and TLS negotiation when needed;
request and response network travel; server request handling, authentication,
throttling, validation, database matching, the separate comic-metadata query,
and response serialization; receiving the complete JSON body; Android JSON parsing
and basic result-shape validation; response cleanup; and returning to the UI thread.
Connection reuse may avoid DNS/connection/TLS setup on a particular request.

Excludes building result cards, downloading/displaying cover artwork, human match
selection, and feedback submission.

### User Experience

Derived sum: **Android client hash processing + API round trip**.

This is not one continuously running timer and is not the complete human scan
experience. The gap between its component timers is excluded: bitmap recycling,
returning from the hash task, and updating the “Searching Metron…” UI. It also
excludes capture, corner adjustment/perspective correction, preview/confirmation,
human decisions, result rendering, artwork loading, and feedback submission.

Postgres hash search is already included in API round trip. Do not add it again.
Per-comic processing-work totals sum these measurements over the one or two
attempts reconstructed for that comic, without adding the human retry delay.

## Validation Exclusion

Trial 7 (Absolute Wonder Woman #12 variant) and original attempts 8 and 9 are excluded from all charts, outcome/rank statistics, and timing statistics because the user confirmed the cover was not represented in Metron. Raw notes are retained unchanged. Included sample: 138 comic trials and 167 attempts.
