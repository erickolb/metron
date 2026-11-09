# CPHTest — Cover Perceptual Hash Test

A display-only Android experiment for Metron nearest-cover search. Application ID: `cloud.metron.cphtest`; version 0.1.0 (1).

## Android Studio

Open this `android` directory as a project, allow Gradle sync, select a test device, and Run the `app` configuration. It uses JDK 17+ (Android Studio's bundled JBR works), Android SDK 36, and minimum Android 8.0/API 26. The checked-in Gradle wrapper is included; `local.properties` remains machine-local. No secrets are embedded in the APK.

The first screen contains **Configuration** and **Image Search**. Configure the instance base URL and an API key issued by that instance. URL and token are encrypted with an Android Keystore-backed AES-GCM key; backups and configuration screenshots are disabled. HTTP is allowed for local test instances; use HTTPS for remote instances. API credentials are sent only to the configured search endpoint, never to artwork hosts or redirects.

Image Search starts the same Google ML Kit document scanner used in Lumiere: one-page camera capture, four editable corners, perspective correction, and JPEG output in base scanner mode. Inspect the corrected preview, then choose **Confirm and search**. Hash calculation happens on-device and only the 16-character hash is sent to Metron. The app displays the eight ranked matches, their matched artwork and bit distances, database matching milliseconds (when enabled), image/hash time, and API round trip. It does not change a collection or upload captures.

Google Play services supplies the scanner UI and downloads it on first use; a compatible device and connectivity for that initial download are needed. Camera access is handled by the scanner service, so the app does not request an independent camera permission. Test actual corner editing and camera behavior on your physical device.

For the prepared local Metron instance, use the USB forwarding or emulator setup in [the experiment guide](../docs/COVER_HASH_EXPERIMENT.md#local-testing). The local API key is in the ignored `.work/metron-local/cphtest-connection.json` at the repository root.

## Build and verify

```powershell
# JAVA_HOME may point to Android Studio's bundled jbr directory.
./gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

The debug APK is `app/build/outputs/apk/debug/app-debug.apk`. No phone installation or public release is performed automatically. Camera captures stay in the app's private cache and are overwritten by the next capture; app removal clears them. Returning after an activity recreation restores the last corrected capture for confirmation rather than silently repeating an API call.

`PerceptualHash.kt` implements 64-bit ImageHash pHash (32×32 Pillow-style luminance/Lanczos preprocessing, DCT-II, top-left 8×8 median threshold including DC). Golden vectors target Pillow 13's adaptive resize pass order; server hashes produced with other preprocessing versions can differ slightly, which nearest-distance ranking accommodates. Regenerate vectors from the repo root with:

```powershell
.venv/Scripts/python.exe android/tools/generate_hash_vectors.py
```

The hash source and tests are platform-independent Kotlin. The API tests use MockWebServer; they never read real credentials or call a live Metron instance. Library licenses remain with their respective authors (AndroidX/OkHttp Apache 2.0, Google ML Kit terms); the enclosing Metron repository license applies to this client source.
