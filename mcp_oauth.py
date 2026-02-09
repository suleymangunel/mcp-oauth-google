"""MCP OAuth2 + Google Login (JWKS verification)"""
import json, secrets, time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse, urlencode
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.provider import OAuthAuthorizationServerProvider, AuthorizationParams, AuthorizationCode
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

class _TokenStore:
    def __init__(self, p):
        self.path, self.data = Path(p), {"clients": {}, "access_tokens": {}, "refresh_tokens": {}}
        if self.path.exists():
            try: self.data.update(json.loads(self.path.read_text()))
            except Exception: pass
    def save(self): self.path.write_text(json.dumps(self.data, indent=2, default=str))

class GoogleJWKSValidator:
    JWKS_URL, ISSUER = "https://www.googleapis.com/oauth2/v3/certs", "https://accounts.google.com"
    def __init__(self, cid):
        self.client_id, self._jwks_cache, self._cache_time, self._cache_ttl = cid, None, 0, 3600
    async def _fetch_jwks(self):
        import httpx
        if self._jwks_cache and (time.time() - self._cache_time) < self._cache_ttl: return self._jwks_cache
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(self.JWKS_URL); r.raise_for_status()
            self._jwks_cache, self._cache_time = r.json(), time.time(); return self._jwks_cache
    async def verify_id_token(self, id_token: str) -> dict:
        try: from jose import jwt, JWTError
        except ImportError: raise ImportError("python-jose gerekli: pip install python-jose[cryptography]")
        jwks = await self._fetch_jwks()
        try: hdr = jwt.get_unverified_header(id_token)
        except JWTError as e: raise ValueError(f"Token header okunamadı: {e}")
        kid = hdr.get("kid")
        if not kid: raise ValueError("Token'da kid bulunamadı")
        rsa_key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not rsa_key: raise ValueError(f"kid={kid} için public key bulunamadı")
        try:
            payload = jwt.decode(id_token, rsa_key, algorithms=["RS256"], audience=self.client_id,
                issuer=self.ISSUER, options={"verify_signature":True,"verify_aud":True,"verify_iss":True,"verify_exp":True,"verify_at_hash":False})
        except JWTError as e: raise ValueError(f"Token doğrulama hatası: {e}")
        if not payload.get("email_verified"): raise ValueError("Email doğrulanmamış")
        return payload

class MCPOAuthProvider(OAuthAuthorizationServerProvider):
    def __init__(self, store, base_url, token_ttl=3600, google_client_id="", google_client_secret="", allowed_emails=None):
        self.store, self.base_url, self.token_ttl = store, base_url.rstrip("/"), token_ttl
        self.google_client_id, self.google_client_secret = google_client_id, google_client_secret
        self.allowed_emails = allowed_emails
        if not google_client_id or not google_client_secret: raise ValueError("google_client_id ve google_client_secret zorunludur.")
        self.jwks_validator = GoogleJWKSValidator(google_client_id)
        self._auth_codes, self._pending_auth, self._auth_code_users = {}, {}, {}

    async def get_client(self, cid):
        d = self.store.data["clients"].get(cid); return OAuthClientInformationFull.model_validate(d) if d else None
    async def register_client(self, ci):
        self.store.data["clients"][ci.client_id] = ci.model_dump(mode="json"); self.store.save()

    async def authorize(self, client, params):
        sid = secrets.token_urlsafe(24)
        self._pending_auth[sid] = {"client_id": client.client_id, "params": {
            "redirect_uri": str(params.redirect_uri), "state": params.state,
            "code_challenge": params.code_challenge, "scopes": params.scopes or [],
            "resource": getattr(params, "resource", None),
            "redirect_uri_provided_explicitly": params.redirect_uri is not None}}
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode({'client_id':self.google_client_id,'redirect_uri':f'{self.base_url}/auth/callback','response_type':'code','scope':'openid email profile','state':sid,'access_type':'offline','prompt':'consent'})}"

    async def complete_google_callback(self, code, state):
        pending = self._pending_auth.pop(state, None)
        if not pending: raise ValueError("Geçersiz veya süresi dolmuş state")
        tr = await self._exchange_google_code(code)
        id_token = tr.get("id_token")
        if not id_token: raise ValueError("Google'dan id_token alınamadı")
        payload = await self.jwks_validator.verify_id_token(id_token)
        user_email = payload.get("email")
        if not user_email: raise ValueError("Token'da email bulunamadı")
        print(f"✔ JWKS doğrulaması başarılı: {user_email} - {payload.get('name','')} - verified:{payload.get('email_verified')}")
        if self.allowed_emails and user_email not in self.allowed_emails:
            raise ValueError(f"Bu kullanıcı ({user_email}) izin listesinde değil.")
        p = pending["params"]; mcp_code = secrets.token_urlsafe(32)
        self._auth_codes[mcp_code] = AuthorizationCode(code=mcp_code, client_id=pending["client_id"],
            redirect_uri=p["redirect_uri"], redirect_uri_provided_explicitly=p["redirect_uri_provided_explicitly"],
            code_challenge=p["code_challenge"], scopes=p["scopes"], expires_at=time.time()+300, resource=p["resource"])
        self._auth_code_users[mcp_code] = user_email
        qp = {"code": mcp_code}
        if p["state"]: qp["state"] = p["state"]
        return f"{p['redirect_uri']}{'&' if '?' in p['redirect_uri'] else '?'}{urlencode(qp)}"

    async def _exchange_google_code(self, code):
        import httpx
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post("https://oauth2.googleapis.com/token", data={"code":code,"client_id":self.google_client_id,
                "client_secret":self.google_client_secret,"redirect_uri":f"{self.base_url}/auth/callback","grant_type":"authorization_code"})
            r.raise_for_status(); return r.json()

    async def load_authorization_code(self, client, ac):
        a = self._auth_codes.get(ac)
        if not a or a.client_id != client.client_id: return None
        if a.expires_at < time.time(): self._auth_codes.pop(ac, None); return None
        return a

    def _make_tokens(self, client_id, user, scopes):
        at, rt = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.store.data["access_tokens"][at] = {"client_id":client_id,"user":user,"scopes":scopes,"expires_at":time.time()+self.token_ttl}
        self.store.data["refresh_tokens"][rt] = {"client_id":client_id,"user":user,"scopes":scopes}
        self.store.save()
        return OAuthToken(access_token=at, token_type="Bearer", expires_in=self.token_ttl, refresh_token=rt, scope=" ".join(scopes) if scopes else None)

    async def exchange_authorization_code(self, client, ac):
        self._auth_codes.pop(ac.code, None); user = self._auth_code_users.pop(ac.code, "unknown")
        return self._make_tokens(client.client_id, user, ac.scopes)

    async def load_access_token(self, token):
        d = self.store.data["access_tokens"].get(token)
        if not d: return None
        if d["expires_at"] < time.time(): self.store.data["access_tokens"].pop(token, None); self.store.save(); return None
        return SimpleNamespace(**d, token=token)

    async def load_refresh_token(self, client, rt):
        d = self.store.data["refresh_tokens"].get(rt)
        return SimpleNamespace(**d, token=rt) if d and d["client_id"] == client.client_id else None

    async def exchange_refresh_token(self, client, rt, scopes):
        self.store.data["refresh_tokens"].pop(rt.token, None)
        return self._make_tokens(client.client_id, rt.user, scopes or rt.scopes)

    async def revoke_token(self, token):
        t = token.token if hasattr(token, "token") else ""
        self.store.data["access_tokens"].pop(t, None); self.store.data["refresh_tokens"].pop(t, None); self.store.save()

def create_oauth_mcp(name, base_url, google_client_id, google_client_secret, allowed_emails=None, store_path=".oauth_store.json", token_ttl=3600, **kw):
    store = _TokenStore(store_path)
    provider = MCPOAuthProvider(store, base_url, token_ttl, google_client_id, google_client_secret, allowed_emails)
    hostname = urlparse(base_url).hostname
    from starlette.requests import Request
    from starlette.responses import RedirectResponse, PlainTextResponse
    from starlette.routing import Route
    async def google_callback(request: Request):
        code, state = request.query_params.get("code"), request.query_params.get("state")
        if not code or not state: return PlainTextResponse("Missing code or state", status_code=400)
        try: return RedirectResponse(url=await provider.complete_google_callback(code=code, state=state))
        except Exception as e: return PlainTextResponse(f"Auth error: {e}", status_code=400)
    mcp = FastMCP(name, auth_server_provider=provider, auth=AuthSettings(
        issuer_url=base_url, resource_server_url=f"{base_url}/mcp",
        revocation_options=RevocationOptions(enabled=True),
        client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=["read","write"], default_scopes=["read"]),
        required_scopes=["read"]),
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[hostname, f"{hostname}:3000"]), **kw)
    mcp._custom_starlette_routes.extend([Route("/auth/callback", endpoint=google_callback, methods=["GET"])])
    return mcp
