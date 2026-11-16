# Agent Pages

Interactive pages for AI agents: web UI, iMessage companion, and self-hosted server. Hermes integration; OpenClaw adapter planned.

Local extraction candidate. No remote is configured. Requires Node 22+, Python 3.9+, macOS with Xcode 16+ and XcodeGen for iOS (iOS 18+). The static web renderer and Python server run independently of any agent framework.

```sh
npm ci
npm run build
npm test
npm run test:form # Chrome installed, or set CHROME_PATH
python3 server/server.py --root apps/web --state .state --private-port 19133 --public-port 19134
```

The server does not serve the form at / or /form.html. Open the separate file apps/web/build/form.html for a synthetic interactive form. The form stores state only in the browser. Build output is not published automatically.

```sh
xcodegen generate --spec apps/ios/project.yml
xcodebuild -project apps/ios/HermesPages.xcodeproj -scheme HermesPages -sdk iphonesimulator -configuration Debug CODE_SIGNING_ALLOWED=NO build
```

Signing fields are blank; see apps/ios/Signing.xcconfig.example. Set your own bundle IDs, app groups and signing settings for devices. Simulator builds include host, Messages and Quick Look extensions. Existing Hermes document type identifiers remain for wire compatibility.

See docs/self-host.md, docs/security.md and docs/attribution.md. OpenClaw is roadmap only. The Hermes delivery adapter is extracted existing code, with mocked transport tests; native live delivery is not validated in this extraction.

No blanket license is granted: neither original source has a root license or package license field. Permission to redistribute or reuse first-party code must be resolved with its rights holders. Third-party font and dependency licenses remain applicable.
