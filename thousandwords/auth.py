from operator import truediv
import os
import click
import requests
import secrets
import base64
import hashlib
import time
import webbrowser
from posixpath import join as urljoin
from logging import getLogger
from getpass import getpass
from configparser import ConfigParser
from requests.auth import AuthBase
from urllib.parse import urlencode, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

from .config import CONFIG

logger = getLogger("thousandwords.auth")

AUTH_REDIRECT_PORTS = [20005, 20015, 20025]

class TokenNotFoundException(Exception):
  def __str__(self) -> str:
    return "No valid auth token. Run `thousandwords login` first."

class TokenExpiredException(Exception):
  def __str__(self) -> str:
    return "Your auth token has expired. Run `thousandwords login` to refresh."

class CognitoJwtAuth(AuthBase):
  """Authorization: JWT_TOKEN"""

  def __init__(self):
    self._jwt_token = CONFIG.jwt_token

  def __eq__(self, other):
    return self._jwt_token == other._jwt_token

  def __ne__(self, other):
    return not self == other

  def __call__(self, r):
    if not self._jwt_token:
      auth = CognitoAuth()
      self._jwt_token = auth.get_or_refresh_token()
    r.headers["Authorization"] = self._jwt_token
    return r

class CallbackServerHandler(BaseHTTPRequestHandler):
  def log_message(self, format, *args):
    logger.debug(format % args)

  def do_GET(self):
    ret = parse_qs(urlparse(self.path).query)
    logger.debug(f"Received local auth callback: {ret}")

    self.server.code = ret["code"][0]
    self.server.state = ret["state"][0]

    self.send_response(301)
    self.send_header("Location", "https://1000words-hq.com/login-success")
    self.end_headers()

class CallbackServer(HTTPServer):
  def __init__(self, *args, **kwargs):
    # Because HTTPServer is an old-style class, super() can't be used.
    HTTPServer.__init__(self, *args, **kwargs)
    self.code = None
    self.state = None

class CognitoAuth:
  def __init__(self):
    self._code = None
    self._code_verifier = None

  def is_authd(self) -> bool:
    try:
      self.get_or_refresh_token()
      return True
    except Exception:
      return False

  def fetch_new_tokens(self) -> None:
    try:
      webbrowser.get()
      has_browser = True
    except:
      has_browser = False
    
    if has_browser:
      redirect_uri = self._fetch_authorization_code_with_browser()
    else:
      redirect_uri = self._fetch_authorization_code_inline()

    params = {
      "grant_type": "authorization_code",
      "code": self._code,
      "code_verifier": self._code_verifier,
      "redirect_uri": redirect_uri,
      "client_id": CONFIG.user_pool_client_id,
    }
    response = requests.post(CONFIG.cognito_token_url, data=params)
    response.raise_for_status()
    tokens = self._parse_token_response(response)
    self._save_tokens(tokens)

  def get_or_refresh_token(self) -> str:
    tokens = self._load_tokens()
    if time.time() > tokens["expiration"]:
      try:
        tokens = self._refresh_tokens(tokens["refresh"])
      except:
        raise TokenExpiredException
    return tokens["id"]

  def _load_tokens(self) -> dict:
    fname = CONFIG.jwt_tokens_path
    logger.info(f"Loading tokens from {fname}")
    tokfile = ConfigParser()
    tokfile.read(fname)
    try:
      tokens = dict(tokfile[CONFIG.instance])
      tokens["expiration"] = int(tokens["expiration"])
      assert "id" in tokens
      return tokens
    except Exception as e:
      logger
      raise TokenNotFoundException

  def _save_tokens(self, tokens: dict) -> None:
    fname = CONFIG.jwt_tokens_path
    logger.info(f"Saving tokens to {fname}")
    tokens = dict(tokens)
    tokens["expiration"] = str(tokens["expiration"])
    tokfile = ConfigParser()
    tokfile.read(fname)
    tokfile[CONFIG.instance] = tokens
    os.makedirs(os.path.dirname(fname), exist_ok=True)
    with (
      open(os.open(fname, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "w")
    ) as f:
      tokfile.write(f)

  # refresh id/access tokens using previously fetched refresh token
  def _refresh_tokens(self, refresh_token) -> dict:
    logger.info("Attempting to refresh expired tokens.")
    params = {
      "grant_type": "refresh_token",
      "refresh_token": refresh_token,
      "client_id": CONFIG.user_pool_client_id,
      "scope": "email profile openid aws.cognito.signin.user.admin",
    }
    logger.debug(f"POSTing to {CONFIG.cognito_token_url}: {params}")
    response = requests.post(CONFIG.cognito_token_url, data=params)
    logger.debug(f"Received: {response}")
    new_tokens = self._parse_token_response(response)
    new_tokens["refresh"] = refresh_token
    self._save_tokens(new_tokens)
    return new_tokens

  # open browser and allow user to authenticate using selected cognito flow
  # and store returned auth code
  def _fetch_authorization_code_with_browser(self):
    logger.info("Launching browser-based authentication.")
    redirect_uri = self._start_callback_listener()
    auth_url, init_state = self._build_auth_url(redirect_uri)
    try:
      click.launch(auth_url)
      self._httpd.handle_request()
    finally:
      assert init_state == self._httpd.state
      self._code = self._httpd.code
      self._httpd.server_close()
    return redirect_uri
  
  def _fetch_authorization_code_inline(self):
    logger.info("Launching inline authentication.")
    redirect_uri = urljoin(CONFIG.instance_url, "oauth2", "display_code", "")
    auth_url, _ = self._build_auth_url(redirect_uri)
    print(f"Go to this URL in a browser: {auth_url}")
    prompt = "Enter your authorization code: " 
    self._code = getpass(prompt)
    return redirect_uri

  def _build_auth_url(self, redirect_uri):
    self._code_verifier = secrets.token_urlsafe(43)
    code_challenge = base64.urlsafe_b64encode(
      hashlib.sha256(self._code_verifier.encode("utf-8")).digest()
    ).rstrip(b"=")
    state = str(secrets.randbits(64))
    params = {
      "redirect_uri": redirect_uri,
      "response_type": "code",
      "client_id": CONFIG.user_pool_client_id,
      "identity_provider": "COGNITO",
      "scope": "email profile openid aws.cognito.signin.user.admin",
      "state": state,
      "code_challenge": code_challenge,
      "code_challenge_method": "S256",
    }

    return f"{CONFIG.cognito_auth_url}?{urlencode(params)}", state

  def _start_callback_listener(self):
    for port in AUTH_REDIRECT_PORTS:
      try:
        self._httpd = CallbackServer(("", int(port)), CallbackServerHandler)
        return f"http://localhost:{port}/"
      except OSError as e:
        if e.errno == 48:
          continue
        else:
          raise Exception("error during authentication: " + e)
    else:
      raise e

  def _parse_token_response(self, response):
    response_json = response.json()
    if "error" in response_json:
      raise Exception(response_json["error"])

    now = int(time.time())
    expires_in = response_json.get("expires_in")
    expiration = now if not expires_in else now + int(expires_in)

    return {
      "access": response_json.get("access_token"),
      "id": response_json.get("id_token"),
      "refresh": response_json.get("refresh_token"),
      "expiration": expiration,
    }
