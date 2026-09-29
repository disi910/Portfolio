"""One-time helper: get a Spotify refresh token for the feed service.

1. Create an app at https://developer.spotify.com/dashboard and add the redirect URI
   http://127.0.0.1:8888/callback
2. Run:  SPOTIFY_CLIENT_ID=... SPOTIFY_CLIENT_SECRET=... python scripts/spotify_auth.py
3. Open the printed URL, approve, and copy the refresh token into .env as SPOTIFY_REFRESH_TOKEN.

Only the scopes needed for the music window are requested (read-only).
"""

import base64
import json
import os
import secrets
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-currently-playing user-read-recently-played"

client_id = os.environ["SPOTIFY_CLIENT_ID"]
client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
state = secrets.token_urlsafe(16)

auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
    "client_id": client_id,
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPES,
    "state": state,
})


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if qs.get("state", [None])[0] != state or "code" not in qs:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"State mismatch or missing code.")
            return
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        req = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=urllib.parse.urlencode({
                "grant_type": "authorization_code",
                "code": qs["code"][0],
                "redirect_uri": REDIRECT_URI,
            }).encode(),
            headers={"Authorization": f"Basic {basic}"},
        )
        with urllib.request.urlopen(req) as resp:
            token = json.load(resp)
        print("\nSPOTIFY_REFRESH_TOKEN=" + token["refresh_token"] + "\n")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Done - check your terminal. You can close this tab.")

    def log_message(self, *args):
        pass


print("Open this URL in your browser:\n\n" + auth_url + "\n")
HTTPServer(("127.0.0.1", 8888), Handler).handle_request()
