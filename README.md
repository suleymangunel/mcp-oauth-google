<div class="sag">
    <th><img alt="GitHub License" src="https://img.shields.io/github/license/suleymangunel/ePaperV2?style=plastic&label=License"></th>
    <th><img alt="Static Badge" src="https://img.shields.io/badge/Language-Python-green?style=plastic"></th>
</div>

# mcp-oauth-google

Google OAuth2 authentication provider for MCP servers.

A lightweight Python module that adds **Google Login** to [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) servers. Verifies Google ID tokens cryptographically using Google's JWKS endpoint — no third-party verification service required.

## Features

- Google OAuth2 + OpenID Connect integration
- Cryptographic token verification via JWKS (with public key caching)
- MCP spec-compliant OAuth2 authorization server provider
- Dynamic client registration
- Access / refresh token management and revocation
- Email whitelist for access control
- Single file, minimal dependencies

## Installation

```bash
pip install mcp httpx python-jose[cryptography] uvicorn starlette
```

## Setup

### 1. Getting Google OAuth2 Credentials

You need a **Client ID** and **Client Secret** from Google Cloud Console.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Navigate to **APIs & Services** → **Credentials**
4. Click **+ CREATE CREDENTIALS** → **OAuth client ID**
5. If prompted, configure the **OAuth consent screen** first:
   - Choose **External** user type
   - Fill in the app name and your email
   - Add the scope `openid`, `email`, `profile`
   - Add your email to **Test users** (required while in "Testing" mode)
6. Back in Credentials, select **Web application** as the application type
7. Under **Authorized redirect URIs**, add:
   ```
   https://<your-tunnel-url>/auth/callback
   ```
   (You'll get this URL in the next step — you can come back and add it)
8. Click **Create** and copy your **Client ID** and **Client Secret**

> **Note:** While the app is in "Testing" mode, only users listed in the OAuth consent screen's test users can log in. To allow any Google account, publish the app.

### 2. Creating a Tunnel with Cloudflare (BASE_URL)

Your MCP server needs a public HTTPS URL. The easiest way during development is a [Cloudflare Quick Tunnel](https://try.cloudflare.com/).

**Install cloudflared:**

```bash
# macOS
brew install cloudflare/cloudflare/cloudflared

# Debian / Ubuntu
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# Windows — download from:
# https://github.com/cloudflare/cloudflared/releases/latest
```

**Start a quick tunnel:**

```bash
cloudflared tunnel --url http://localhost:3000
```

You'll see output like:

```
+----------------------------+
| Your quick tunnel is ready! |
| https://random-words-here.trycloudflare.com |
+----------------------------+
```

Copy this URL — this is your `BASE_URL`.

> **Important:** Quick tunnel URLs change every time you restart cloudflared. After getting a new URL, update `BASE_URL` in `server.py` **and** the redirect URI in Google Cloud Console.

### 3. Configure server.py

```python
BASE_URL = "https://random-words-here.trycloudflare.com"  # from step 2
GOOGLE_CLIENT_ID = "123456789-xxxxx.apps.googleusercontent.com"  # from step 1
GOOGLE_CLIENT_SECRET = "GOCSPX-xxxxx"  # from step 1

ALLOWED_EMAILS = {"you@gmail.com"}  # set to None to allow all Google accounts
```

### 4. Update Google Redirect URI

Go back to [Google Cloud Console](https://console.cloud.google.com/) → **Credentials** → your OAuth client, and make sure the redirect URI matches:

```
https://<your-BASE_URL>/auth/callback
```

## Usage

### server.py

```python
from mcp_oauth import create_oauth_mcp

mcp = create_oauth_mcp(
    name="MyServer",
    base_url="https://<tunnel-url>",
    google_client_id="xxx.apps.googleusercontent.com",
    google_client_secret="GOCSPX-xxx",
    allowed_emails={"user1@gmail.com", "user2@gmail.com"},  # None = allow all
)

@mcp.tool()
async def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=3000)
```

Run:

```bash
python server.py
```

### Access Control

The `allowed_emails` parameter controls who can log in:

```python
# Only specific users
allowed_emails={"alice@gmail.com", "bob@gmail.com"}

# Any authenticated Google account
allowed_emails=None
```

## Connecting

### Claude / ChatGPT MCP Connector

| Field | Value |
|-------|-------|
| MCP Server URL | `https://<tunnel-url>/mcp` |
| Authentication | OAuth |
| Client ID | *(leave empty — dynamic registration)* |
| Client Secret | *(leave empty)* |

### Google Cloud Console

| Field | Value |
|-------|-------|
| Authorized redirect URI | `https://<tunnel-url>/auth/callback` |

## Auth Flow

```
Client (Claude/ChatGPT)
  │
  ├─► MCP Server /authorize
  │     └─► Google OAuth2 consent screen
  │           └─► Google callback → /auth/callback
  │                 ├─ Google code → token exchange
  │                 ├─ ID token JWKS verification
  │                 ├─ Email whitelist check
  │                 └─► Redirect to client (with MCP auth code)
  │
  ├─► /token (code → access_token + refresh_token)
  └─► /mcp (tool calls with Bearer token)
```

## Parameters

`create_oauth_mcp()` accepts the following:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | ✓ | MCP server name |
| `base_url` | ✓ | Server's public HTTPS URL |
| `google_client_id` | ✓ | Google OAuth2 Client ID |
| `google_client_secret` | ✓ | Google OAuth2 Client Secret |
| `allowed_emails` | | Set of allowed emails, or `None` to allow all (default: `None`) |
| `store_path` | | Token store file path (default: `.oauth_store.json`) |
| `token_ttl` | | Access token lifetime in seconds (default: `3600`) |

## Project Structure

```
├── mcp_oauth.py    # OAuth2 provider + JWKS validator module
├── server.py       # Example MCP server
└── README.md
```

## Security Notes

- Google's public keys are fetched from the JWKS endpoint and cached for 1 hour
- Token signature, audience, issuer, and expiry are cryptographically verified
- Access can be restricted to specific Google accounts via `allowed_emails`
- The token store file (`.oauth_store.json`) contains sensitive data — add it to `.gitignore`

## License

MIT
