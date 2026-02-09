# mcp-oauth-google

A lightweight Python module that adds **Google Login** OAuth2 authentication to [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) servers.

Verifies Google ID tokens using Google's JWKS (JSON Web Key Set) endpoint — no third-party verification service required.

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

## Prerequisites

### Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**
2. Create an **OAuth 2.0 Client ID** (Web application)
3. Add the following as an **Authorized redirect URI**:
   ```
   https://<your-domain>/auth/callback
   ```
4. Note your `Client ID` and `Client Secret`

### Tunnel (for development)

You can use a tunneling service like Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://localhost:3000
```

Use the tunnel URL as `BASE_URL` and as the redirect URI in Google Console.

## Usage

### server.py

```python
from mcp_oauth import create_oauth_mcp

mcp = create_oauth_mcp(
    name="MyServer",
    base_url="https://<tunnel-url>",          # Your server's public URL
    google_client_id="xxx.apps.googleusercontent.com",
    google_client_secret="GOCSPX-xxx",
)

# Define your tools
@mcp.tool()
async def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.tool()
async def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=3000)
```

### Access Control

Edit the `ALLOWED_EMAILS` set in `mcp_oauth.py`:

```python
ALLOWED_EMAILS = {"user1@gmail.com", "user2@gmail.com"}
```

Only Google accounts in this set can access the server.

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

## Project Structure

```
├── mcp_oauth.py    # OAuth2 provider + JWKS validator module
├── server.py       # Example MCP server
└── README.md
```

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

`create_oauth_mcp()` accepts the following parameters:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | ✓ | MCP server name |
| `base_url` | ✓ | Server's public URL |
| `google_client_id` | ✓ | Google OAuth2 Client ID |
| `google_client_secret` | ✓ | Google OAuth2 Client Secret |
| `store_path` | | Token store file path (default: `.oauth_store.json`) |
| `token_ttl` | | Access token lifetime in seconds (default: `3600`) |

## Security Notes

- Google's public keys are fetched from the JWKS endpoint and cached for 1 hour
- Token signature, audience, issuer, and expiry are cryptographically verified
- Access is restricted via the `ALLOWED_EMAILS` whitelist
- The token store file (`.oauth_store.json`) contains sensitive data — add it to `.gitignore`

## License

MIT
