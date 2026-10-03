# DigitalBurj HQ for Android

A small, hardened WebView shell around <https://hq.digitalburj.com>. All logic, permissions and data stay on
the server, so the app is always as current as the website and has no separate backend to secure.

## What the app does

- Loads only the HQ origin inside the app. Other links open in the browser, mail or phone app.
- Edge-to-edge layout with correct status-bar, navigation-bar and keyboard handling.
- Uploads use the system picker (camera, gallery, files). Downloads use the system download manager;
  the session cookie is sent only to `hq.digitalburj.com`, never to the storage host.
- Offline or unreachable: shows a local page and reconnects automatically when the network returns.
- The back button closes dialogs and drawers, leaves a chat thread, and returns to Overview before exiting.
- Release builds block screenshots and the recent-apps thumbnail (`FLAG_SECURE`) to protect private documents.
- No JavaScript bridge, no file or content access, cleartext traffic blocked, backups disabled.
- Adaptive and themed (monochrome) launcher icon, splash screen, R8 minification and resource shrinking.

## Build

The Android SDK is not needed to work on the website. CI builds the app on every change under `android/`
(workflow *Android app*) and uploads the debug APK, release APK and release bundle as artifacts.

Locally, with JDK 17, the Android SDK and Gradle 8.10:

```
gradle -p android :app:assembleDebug     # installable test build (com.digitalburj.hq.debug)
gradle -p android :app:assembleRelease   # optimized build
```

## Signing a Play Store release

Without a keystore the release build is signed with the debug key: fine for internal installs, not accepted by
Google Play. To sign properly, create a keystore **once and keep it safe** (losing it means you can never update
the published app), then provide these environment variables (in CI: repository secrets):

| Variable | Meaning |
| --- | --- |
| `HQ_KEYSTORE` | path to the keystore file |
| `HQ_KEYSTORE_PASSWORD` | keystore password |
| `HQ_KEY_ALIAS` | key alias |
| `HQ_KEY_PASSWORD` | key password |

`HQ_VERSION_CODE` (set from the CI run number) must increase with every upload.

## Where the app is pointed

`HQ_URL` and `HQ_HOST` in `app/build.gradle.kts`. Change both (and the host in `AndroidManifest.xml`) to
point a build at another deployment.
