import boto3
from logging import getLogger
from configparser import ConfigParser
import os
from thousandwords.config import CONFIG
from thousandwords.auth import CognitoAuth

logger = getLogger("thousandwords.credentials")

class GuestNotFoundException(Exception):
  def __str__(self) -> str:
    return "No IdentityId for guest found"

class CognitoCredentials:
  def __init__(self):
    self._cognito = boto3.Session(region_name=CONFIG.cognito_region).client('cognito-identity')
    self._credentials = None
  
  @property
  def credentials(self):
    if self._credentials is None:
      auth = CognitoAuth()
      if auth.is_authd():
        jwt_token = auth.get_or_refresh_token()
        logins = {
          f"cognito-idp.{CONFIG.cognito_region}.amazonaws.com/{CONFIG.user_pool_id}": jwt_token
        }
        resp = self._cognito.get_id(
          IdentityPoolId=CONFIG.identity_pool_id,
          Logins=logins
        )
        identityId = resp['IdentityId']
        resp = self._cognito.get_credentials_for_identity(
          IdentityId=identityId,
          Logins=logins
        )
        self._credentials = resp
      else:
        identityId = self.guest_identity_id
        resp = self._cognito.get_credentials_for_identity(IdentityId=identityId)
        self._credentials = resp
    return self._credentials
  
  @property
  def guest_identity_id(self) -> str:
    try:
      id = self._load_guest_identity_id()
    except GuestNotFoundException:
      resp = self._cognito.get_id(IdentityPoolId=CONFIG.identity_pool_id)
      id = resp['IdentityId']
      self._save_guest_identity_id(id)
    return id

  def _load_guest_identity_id(self) -> str:
    fname = CONFIG.guest_id_path
    logger.info(f"Loading identityid from {fname}")
    idfile = ConfigParser()
    idfile.read(fname)
    try:
      id = dict(idfile[CONFIG.instance])
      return id['identityid']
    except Exception as e:
      logger
      raise GuestNotFoundException

  def _save_guest_identity_id(self, id: str) -> None:
    fname = CONFIG.guest_id_path
    logger.info(f"Saving identityid to {fname}")
    id = {'identityid': id}
    idfile = ConfigParser()
    idfile.read(fname)
    idfile[CONFIG.instance] = id
    os.makedirs(os.path.dirname(fname), exist_ok=True)
    with (
      open(os.open(fname, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "w")
    ) as f:
      idfile.write(f)
