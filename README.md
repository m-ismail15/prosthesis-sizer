PROSTHESIS SIZING APPLICATION
User Guide & Deployment Notes
=============================

OVERVIEW
This application calculates prosthesis sizes based on user measurements and stores records securely using Firebase.

The application is distributed as a standalone Windows executable and does NOT require Python installation.

---

## FILES INCLUDED

app.exe                     → Main application
serviceAccountKey.json      → Firebase authentication key (required)
README.txt                  → This guide

---

## IMPORTANT: FIREBASE KEY LOCATION

The file `serviceAccountKey.json` MUST be in the SAME folder as `app.exe`.

Correct structure:

```
Prosthesis_App/
├── app.exe
├── serviceAccountKey.json
└── README.txt
```

If the key is missing or in another location, the application will not start.

---

## HOW TO RUN THE APPLICATION

1. Double-click `app.exe`
2. The login screen will appear.
3. Enter your credentials.
4. Use the interface to search, add, or view records.

---

## PORTABILITY

You can move the entire folder to:
• Another location on the same computer
• A USB drive
• Another Windows PC

As long as `app.exe` and `serviceAccountKey.json` stay together, the app will run.

---

## SECURITY NOTICE

The Firebase key provides secure access to the database.

DO NOT:
• Upload the key to GitHub or public websites
• Email the key without encryption
• Share the key with unauthorized users

If the key is exposed:

1. Revoke it in Firebase Console
2. Generate a new key
3. Replace the old file

---

## TROUBLESHOOTING

Problem: App does not open
Solution:
• Ensure `serviceAccountKey.json` is in the same folder.

Problem: "Firebase key not found" error
Solution:
• Verify file name is exactly: serviceAccountKey.json
• Ensure file is not inside another folder.

Problem: App opens then closes immediately
Solution:
• Run from Command Prompt to see errors:

```
  cd path\to\app
  app.exe
```

---

## FOR SUPERVISORS / DISTRIBUTION

To share the application:

1. Copy the entire folder.
2. Provide each user with:
   • app.exe
   • serviceAccountKey.json
   • README.txt

No installation required.

---

## VERSION

Application: Prosthesis Sizing App
Platform: Windows 10/11
Build Type: PyInstaller Standalone Executable

---

## END OF FILE
