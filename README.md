PROSTHESIS SIZING APPLICATION
User Guide & Deployment Notes
=============================

OVERVIEW
This application calculates prosthesis sizes from user measurements.

It supports two storage modes:
- Online mode: authenticates against Firebase and stores records in Firestore.
- Offline mode: skips Firebase and stores records locally on the device.

The application can still be distributed as a Windows installer and does not require Python installation.

---

## INSTALLED FILES

app.exe                     -> Main application
README.txt                  -> This guide

The application installs its binaries under the program installation folder.

User-specific writable files are stored under:

`%LOCALAPPDATA%\MedTech\Prosthesis Sizing App`

These user files include:

data/offline_records.json   -> Local patient records created while offline
config/serviceAccountKey.json -> Optional Firebase key for online mode

---

## ONLINE MODE

To use online mode, place `serviceAccountKey.json` in one of these locations:

1. The same folder as `app.exe`
2. `config/serviceAccountKey.json` next to `app.exe`
3. `%LOCALAPPDATA%\MedTech\Prosthesis Sizing App\config\serviceAccountKey.json`
4. A path provided by the `FIREBASE_KEY_PATH` environment variable

If the Firebase key is missing, the app still starts and can be used in offline mode.

---

## OFFLINE MODE

From the login screen, select `Continue Offline`.

In offline mode:
- Records are saved to `%LOCALAPPDATA%\MedTech\Prosthesis Sizing App\data\offline_records.json`
- Searches read from the local file only
- Firebase is not required
- Online users and cloud records are not available

You can also force offline startup by setting:

`PROSTHESIS_APP_MODE=offline`

---

## HOW TO RUN THE APPLICATION

1. Double-click `app.exe`
2. Choose one of the following:
   - `Login Online` to use Firebase
   - `Continue Offline` to work locally
3. Use the interface to add, search, or view records

---

## PORTABILITY

You can move the entire folder to:
- Another location on the same computer
- A USB drive
- Another Windows PC

As long as the user profile is writable, offline mode can create and update its local queue file.

---

## SECURITY NOTICE

The Firebase key provides access to the online database.

Do not:
- Upload the key to GitHub or public websites
- Email the key without encryption
- Share the key with unauthorized users

If the key is exposed:

1. Revoke it in Firebase Console
2. Generate a new key
3. Replace the old file

Offline records may contain patient information. Protect the device and the local data file accordingly.

---

## TROUBLESHOOTING

Problem: Online login is unavailable
Solution:
- Use `Continue Offline`
- Verify `serviceAccountKey.json` exists if online mode is required

Problem: Offline mode cannot save records
Solution:
- Ensure the application folder is writable
- Check that `%LOCALAPPDATA%\MedTech\Prosthesis Sizing App\data\offline_records.json` is not locked or corrupted

Problem: The offline data file is invalid
Solution:
- Repair or remove `%LOCALAPPDATA%\MedTech\Prosthesis Sizing App\data\offline_records.json`
- Restart the app to recreate a clean local file

---

## VERSION

Application: Prosthesis Sizing App
Platform: Windows 10/11
Build Type: PyInstaller application packaged into a WiX MSI installer
Current Version Source: `app_version.py`

---

## BUILD NOTES

Source measurement guide images live in:

`images\`

Recommended build order:

1. Build the application bundle:
   `powershell -ExecutionPolicy Bypass -File .\scripts\build_app.ps1`
2. Build the MSI:
   `powershell -ExecutionPolicy Bypass -File .\scripts\build_msi.ps1`

Single-command release build:

`powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1`

To publish a new release:

1. Update `APP_VERSION` in `app_version.py`
2. Run `powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1`
3. Collect the MSI from `build\msi\`

---

## INSTALLATION INSTRUCTIONS

For end users:

1. Locate the MSI file, for example:
   `ProsthesisSizingApp_1.0.0.msi`
2. Double-click the MSI
3. If Windows shows a security prompt, choose `Run`
4. Follow the Windows Installer prompts until setup completes
5. Open the app from the Start Menu entry:
   `Prosthesis Sizing App`

For offline use:

1. Launch the app
2. Select `Continue Offline`
3. Records will be queued in:
   `%LOCALAPPDATA%\MedTech\Prosthesis Sizing App\data\offline_records.json`

For online use:

1. Create this folder if it does not already exist:
   `%LOCALAPPDATA%\MedTech\Prosthesis Sizing App\config`
2. Place `serviceAccountKey.json` in that folder
3. Launch the app
4. Enter your email and password on the login screen
5. Any queued offline records will sync after successful online login

To uninstall:

1. Open `Settings`
2. Go to `Apps`
3. Find `Prosthesis Sizing App`
4. Select `Uninstall`
