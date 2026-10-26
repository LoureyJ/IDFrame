# IDFrame project rules

- After application or deployment code changes, run `.venv\Scripts\python.exe build_release.py --prepare-only` once changes are complete. This updates the client version without building or publishing. Unchanged code must retain the same version.
- The user controls OTA publication. Do not run `update.bat` or publish a release unless the user asks.
- Do not rebuild installers unless the user asks. Preserve existing installers when making changes for a pending OTA update.
- Keep the client version visible in the application. Version information travels with the changed application files through OTA.
- Maintain `assets/changelog.json` with user-facing release notes for each newly prepared client version.

- After completing and validating each requested code update, commit and push it to https://github.com/LoureyJ/IDFrame. Never include host secrets, personal training photos, or local builds. GitHub publication does not authorize LAN OTA publication or rebuilding installers.
