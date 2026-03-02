PROSTHESIS SIZING APPLICATION
User Guide & Deployment Notes
=============================

OVERVIEW
This application calculates prosthesis sizes from user measurements.

It supports two storage modes:
- Online mode: authenticates against Firebase and stores records in Firestore.
- Offline mode: skips Firebase and stores records locally on the device.

The application can still be distributed as a standalone Windows executable and does not require Python installation.

---

## FILES INCLUDED

app.exe                     -> Main application
serviceAccountKey.json      -> Firebase authentication key (required for online mode only)
README.md                   -> This guide

Offline mode also creates:

data/offline_records.json   -> Local patient records created while offline

---

## ONLINE MODE

To use online mode, place `serviceAccountKey.json` in one of these locations:

1. The same folder as `app.exe`
2. `config/serviceAccountKey.json` next to `app.exe`
3. A path provided by the `FIREBASE_KEY_PATH` environment variable

If the Firebase key is missing, the app still starts and can be used in offline mode.

---

## OFFLINE MODE

From the login screen, select `Continue Offline`.

In offline mode:
- Records are saved to `data/offline_records.json`
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

As long as the app folder remains writable, offline mode can create and update `data/offline_records.json`.

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
- Check that `data/offline_records.json` is not locked or corrupted

Problem: The offline data file is invalid
Solution:
- Repair or remove `data/offline_records.json`
- Restart the app to recreate a clean local file

---

## VERSION

Application: Prosthesis Sizing App
Platform: Windows 10/11
Build Type: PyInstaller Standalone Executable
