# Self hosting

Run npm ci and npm run build, then python3 server/server.py --root apps/web --state .state. Both listeners bind loopback: private API 9133, snapshot listener 9134. State holds SQLite snapshot records (there is no API credential); keep it private and persistent. Do not expose the private API publicly.

For Tailscale, install and authenticate your own node, then explicitly configure `tailscale serve --bg --https=443 http://127.0.0.1:9133` for tailnet-only access. Inspect your Tailscale access rules first. Set the resulting HTTPS address in the iOS connection settings and AGENT_PAGES_BASE_URL. Do not enable Funnel for the private API. Public snapshots require a separate HTTPS proxy to 9134 and a public-url.txt in the state directory. This guide does not configure any live service.

For static web hosting, upload only apps/web/build to your static host after reviewing the generated files. Synthetic demo forms are browser-local; static hosting does not provide form storage. Never upload server state or a private Page library.

Optional iCloud copy: explicitly set ICLOUD_PUBLISH_DIR and run python3 adapters/icloud/publish.py. It copies build output only, and is off by default.

Set AGENT_PAGES_ALLOWED_HOSTS to a comma-separated list of additional hostnames for your proxy. Loopback hosts are always allowed. AGENT_PAGES_PRIVATE_PORT and AGENT_PAGES_PUBLIC_PORT or the matching CLI flags select listener ports. No physical device is required; AGENT_PAGES_DEVICE_ID / --device-id is optional metadata reserved for device integrations. Recovery uses only the configured bridge recipient.

The public proxy host must be listed in AGENT_PAGES_ALLOWED_HOSTS.
