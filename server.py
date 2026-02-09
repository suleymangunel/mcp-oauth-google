"""
server.py — Example MCP Server (OAuth2 + Google Login)
======================================================
Usage:
    python server.py

Claude / ChatGPT Connector:
    - MCP Server URL: https://<tunnel-url>/mcp
    - Authentication: OAuth
    - Client ID: leave empty
    - Client Secret: leave empty

Google Cloud Console:
    - Authorized redirect URI: https://<tunnel-url>/auth/callback
"""

from mcp_oauth import create_oauth_mcp

# ============================================================
# SETTINGS — Replace with your own values
# ============================================================

BASE_URL = "your tunnel"
GOOGLE_CLIENT_ID = "Client ID from Google"
GOOGLE_CLIENT_SECRET = "Client Secret from Google"

# Set to None to allow all authenticated Google accounts
ALLOWED_EMAILS = {"suleymangunel@gmail.com"}

# ============================================================
# SERVER
# ============================================================

mcp = create_oauth_mcp(
    name="Demo",
    base_url=BASE_URL,
    google_client_id=GOOGLE_CLIENT_ID,
    google_client_secret=GOOGLE_CLIENT_SECRET,
    allowed_emails=ALLOWED_EMAILS,
)


@mcp.tool()
async def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


@mcp.tool()
async def subtract(a: float, b: float) -> float:
    """Subtract two numbers"""
    return a - b


@mcp.tool()
async def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b


@mcp.tool()
async def divide(a: float, b: float) -> float:
    """Divide two numbers"""
    return a / b


if __name__ == "__main__":
    import uvicorn

    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=3000)