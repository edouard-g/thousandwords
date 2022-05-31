from __future__ import annotations
import logging
from python_graphql_client import GraphqlClient
from typing import Optional
import boto3
from requests_aws4auth import AWS4Auth
from thousandwords.auth import CognitoJwtAuth, CognitoAuth
from thousandwords.config import CONFIG
from thousandwords.credentials import CognitoCredentials

logger = logging.getLogger("thousandwords.client")

class Client:

  def __init__(
    self,
    instance: Optional[str] = None,
  ):
    if instance:
      CONFIG.instance = instance

    self._s3 = None
    self._cognito_creds = CognitoCredentials()
  
  def _get_gql_client(self, auth_type):
    endpoint = CONFIG.api_endpoint
    if auth_type == 'AMAZON_COGNITO_USER_POOLS':
      auth = CognitoJwtAuth()
    elif auth_type == 'AWS_IAM':
      creds = self._cognito_creds.credentials['Credentials']
      is_mock = (endpoint == 'http://192.168.1.30:20002/graphql')
      auth = AWS4Auth(
        # see https://docs.amplify.aws/cli/usage/mock/
        'ASIAVJKIAM-UnAuthRole' if is_mock else creds['AccessKeyId'],
        creds['SecretKey'],
        CONFIG.api_region,
        'appsync',
        session_token=creds['SessionToken'],
      )
    return GraphqlClient(auth=auth, endpoint=endpoint)

  @property
  def instance(self) -> str:
    return CONFIG.instance
  
  def create_cell(self, input):    
    query = """
      mutation CreateCell($input: CreateCellInput!) {
        createCell(input: $input) {
          id
        }
      }
    """
    if CognitoAuth().is_authd():
      auth_type = 'AMAZON_COGNITO_USER_POOLS'
    else:
      # fallback to guest (public iam)
      auth_type = 'AWS_IAM'
    ret = self._get_gql_client(auth_type).execute(
      query=query, variables={"input": input}
    )
    if "errors" in ret:
      raise Exception(ret["errors"][0]["message"])

    return ret["data"]["createCell"]["id"]
  
  def create_invite(self, input):
    query = """
      mutation CreateInvite(
        $input: CreateInviteInput!
      ) {
        createInvite(input: $input) {
          id
        }
      }
    """
    if CognitoAuth().is_authd():
      auth_type = 'AMAZON_COGNITO_USER_POOLS'
    else:
      # fallback to guest (public iam)
      auth_type = 'AWS_IAM'
    ret = self._get_gql_client(auth_type).execute(
      query=query, variables={"input": input}
    )
    if "errors" in ret:
      raise Exception(ret["errors"][0]["message"])

    return ret["data"]["createInvite"]["id"]
  
  def get_callback(self, id):
    query = """
      query GetCallback($id: ID!) {
        getCallback(id: $id) {
          id
        }
      }
    """
    ret = self._get_gql_client('AWS_IAM').execute(
      query=query, variables={"id": id}
    )
    if "errors" in ret:
      raise Exception(ret["errors"][0]["message"])
    return (ret["data"]["getCallback"] or {}).get("id")
  
  def run_cell(self, req):
    query = """
      mutation RunCell($request: ExecuteRequestInput) {
        runCell(request: $request) {
          stdout
          stderr
          outputs {
            representations {
              mime
              key
              width
              height
              data
            }
            metadata
          }
          traceback
          userNS {
            name
            key
            value
            serializationType
          }
        }
      } 
    """
    ret = self._get_gql_client('AWS_IAM').execute(
      query=query, variables={"request": req}
    )
    if "errors" in ret:
      raise Exception(ret["errors"][0]["message"])
    return ret["data"]["runCell"]
  
  @property
  def s3(self):
    if not self._s3:
      self._s3 = self._get_session().client('s3')
    return self._s3
  
  def upload(self, key, value):
    resp = self.s3.put_object(
      Key=key,
      Bucket=CONFIG.storage_bucket,
      Body=value,
    )
    logger.debug(f"s3 put_object response: {resp}")
  
  def get(self, key):
    resp = self.s3.get_object(
      Key=key,
      Bucket=CONFIG.storage_bucket,
    )
    logger.debug(f"s3 get_object response: {resp}")
    return resp['Body'].read()

  def _get_session(self):
    creds = self._cognito_creds.credentials['Credentials']
    return boto3.Session(
      aws_access_key_id=creds['AccessKeyId'],
      aws_secret_access_key=creds['SecretKey'],
      aws_session_token=creds['SessionToken'],
    )