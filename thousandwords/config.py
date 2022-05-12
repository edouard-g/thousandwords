import os
import requests

from logging import getLogger
from pathlib import Path
from posixpath import join as urljoin
from configparser import ConfigParser
from typing import Optional, Dict, Tuple

logger = getLogger("thousandwords.config")

_CONFIG_PATH = os.path.expanduser(
  os.environ.get("THOUSANDWORDS_CONFIG_PATH", os.path.join(Path.home(), ".thousandwords"))
)
_CONFIG_FILE = os.path.join(_CONFIG_PATH, "config")

def _sanitize_instance(instance: str) -> Tuple[str, str]:
  if not instance:
    raise Exception("No instance configured")

  for localhost in ("localhost:", "127.0.0.1:", "0.0.0.0:"):
    if instance.startswith(localhost):
      return "http", instance
    if instance.startswith(f"http://{localhost}"):
      return "http", instance[7:]

  if instance.startswith("http://"):
    raise Exception("Thousandwords Instance URL must start with https://")

  if instance.startswith("https://"):
    return "https", instance[8:]

  return "https", instance


class Config:
  def __init__(self, fname: str = _CONFIG_FILE):
    self._fname = fname
    self._config = ConfigParser()
    self._config.read(fname)

    self._instance: Optional[str] = None
    self._instance_protocol: Optional[str] = None

  def _get(self, key: str) -> Optional[str]:
    # Environment variable first, then config
    env_key = "THOUSANDWORDS_" + key.upper()
    if env_key in os.environ:
      val = os.environ[env_key]
      logger.debug(f"Using ENV['{env_key}'] as {key}: '{val}'")
      return os.environ[env_key]
    if self.instance not in self._config:
      self._config.add_section(self.instance)
    try:
      val = self._config[self.instance][key]
      logger.debug(f"Using '{key}' from config file: '{val}'")
      return val
    except KeyError:
      logger.debug(f"Config variable '{key}' not found.")
      return None

  def _get_or_stack(self, key: str) -> str:
    val = self._get(key)
    if val is None:
      self._update_from_stack(self._fetch_stack())
      val = self._get(key)
    if val is None:
      raise KeyError
    return val

  def _set(self, key: str, val: str) -> None:
    if self.instance not in self._config:
      self._config.add_section(self.instance)
    self._config[self.instance][key] = val

  def _fetch_stack(self) -> Dict[str, str]:
    stack_config_url = urljoin(self.instance_url, "stack.json")
    logger.info(f"Fetching stack config from {stack_config_url}")
    response = requests.get(stack_config_url)
    response.raise_for_status()
    try:
      resp_json: Dict[str, str] = response.json()
      return resp_json
    except:
      raise Exception("error fetching stack config from: " + stack_config_url)

  def _update_from_stack(self, stack: Dict[str, str]) -> None:
    self._set("storage_bucket", stack["aws_user_files_s3_bucket"])
    self._set("user_pool_client_id", stack["aws_user_pools_client_id"])
    self._set("user_pool_id", stack["aws_user_pools_id"])
    cognito_region = stack["aws_cognito_region"]
    self._set("cognito_region", cognito_region)
    self._set("identity_pool_id", stack["aws_cognito_identity_pool_id"])
    user_pool_domain = stack["aws_user_pool_domain"]
    self._set(
      "cognito_auth_url",
      f"https://{user_pool_domain}/login",
    )
    self._set(
      "cognito_token_url",
      f"https://{user_pool_domain}/oauth2/token",
    )
    self._set("api_endpoint", stack["aws_appsync_graphqlEndpoint"])
    self._set("api_region", stack['aws_appsync_region'])
    self.save(update_default_instance=False)

  @property
  def instance(self) -> str:
    if not self._instance:
      self.instance = (
        os.environ.get("THOUSANDWORDS_INSTANCE") 
        or self._config["DEFAULT"].get("instance")
        or '1000words-hq.com'
      )
    return self._instance

  @instance.setter
  def instance(self, instance: str) -> None:
    self._instance_protocol, self._instance = _sanitize_instance(instance)

  @property
  def instance_url(self) -> str:
    instance = self.instance
    return f"{self._instance_protocol}://{instance}"

  @property
  def api_key(self) -> Optional[str]:
    return self._get("api_key")

  @property
  def jwt_token(self) -> Optional[str]:
    return self._get("jwt_token")

  @property
  def jwt_tokens_path(self) -> Optional[str]:
    return self._get("jwt_tokens_path") or os.path.join(_CONFIG_PATH, ".jwt-tokens")
  
  @property
  def guest_id_path(self) -> Optional[str]:
    return self._get("guest_id_path") or os.path.join(_CONFIG_PATH, ".guest-id")

  @property
  def user_pool_id(self) -> str:
    return self._get_or_stack("user_pool_id")
  
  @property
  def cognito_region(self) -> str:
    return self._get_or_stack("cognito_region")
  
  @property
  def identity_pool_id(self) -> str:
    return self._get_or_stack("identity_pool_id")

  @property
  def user_pool_client_id(self) -> str:
    return self._get_or_stack("user_pool_client_id")

  @property
  def cognito_auth_url(self) -> str:
    return self._get_or_stack("cognito_auth_url")

  @property
  def cognito_token_url(self) -> str:
    return self._get_or_stack("cognito_token_url")
  
  @property
  def storage_bucket(self) -> str:
    return self._get_or_stack("storage_bucket")

  @property
  def api_endpoint(self) -> str:
    return self._get_or_stack("api_endpoint")
  
  @property
  def api_region(self) -> str:
    return self._get_or_stack("api_region")

  def save(self, update_default_instance: bool = True) -> None:
    logger.info(f"Saving config to '{self._fname}'")
    if update_default_instance:
      self._config["DEFAULT"]["instance"] = self.instance
    os.makedirs(os.path.dirname(self._fname), exist_ok=True)
    with open(self._fname, "w") as f:
      self._config.write(f)

CONFIG = Config()
