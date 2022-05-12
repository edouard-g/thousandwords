from cProfile import run
import json
import uuid
import sys
from posixpath import join as urljoin
from IPython import get_ipython
from IPython.display import display
from IPython.core.magic import (
  Magics,
  cell_magic,
  magics_class,
)
from nanoid import generate
from thousandwords.auth import CognitoAuth
from thousandwords.cli import login
from thousandwords_core.serializer import Serializer
from .status import Status
from .lint import resolveUndefined
from .client import Client
from .capture import CapturedIO
from .config import CONFIG

def parse_response_output(client: Client, output):
  data = {}
  for repr in output["representations"]:
    if repr.get('data', None) is None:
      d = client.get(repr['key'])
    else:
      d = repr["data"]
    data[repr["mime"]] = d
  return {"metadata": json.loads(output['metadata']), "data": data}

def add_dependency_injection_comment(vnames, lines):
  if len(vnames) > 0:
    lines = [
      '""" 1000words-autogen',
      f"Dependenc{'ies' if len(vnames) > 1 else 'y'} injected: {', '.join(vnames)}",
      '"""',
    ] + lines
  return lines

def get_version():
  major, minor, *_ = sys.version_info
  return f"{major}.{minor}"

class CellLink:
  def __init__(self, id):
    self.url = urljoin(CONFIG.instance_url, f'c/{id}')
  def _repr_pretty_(self, p, cycle):
    firstline = 'Interactive cell available at:'
    n = max(len(firstline), len(self.url))
    p.text('-'*n); p.break_()
    p.text(firstline); p.break_()
    p.text(self.url)

@magics_class
class ShareMagic(Magics):
  def __init__(self, shell):
    Magics.__init__(self, shell=shell)

  @cell_magic("share")
  def cmagic(self, line="", cell=""):
    lines = cell.split('\n')
    try:
      undefs = resolveUndefined(cell)
    except Exception as e:
      print(e, file=sys.stderr)
      return
    
    client = Client()
    def puts3(name, data):
      with Status(f"Uploading dependency '{name}'"):
        return client.upload(str(uuid.uuid4()), data)
    srz = Serializer(puts3)
    vnames = list(set([u.message_args[0] for u in undefs]))
    for vname in vnames:
      try:
        obj = self.shell.user_ns[vname]
      except KeyError:
        print(f"Dependency '{vname}' is not defined", file=sys.stderr)
        return
      try:
        srz.add(vname, obj)
      except Exception as err:
        print(f"Could not serialize {vname}: {err}", file=sys.stderr)
        return

    lines = add_dependency_injection_comment(vnames, lines)
    run_request = {"lines": lines, "userNS": srz.ns, "version": get_version()}
    try:
      with Status("Running cell"):
        run_reply = client.run_cell(run_request)
    except Exception as err:
      print(err, file=sys.stderr)
      return
  
    io = CapturedIO(
      run_reply['stdout'],
      run_reply['stderr'],
      run_reply['traceback'],
      [parse_response_output(client, o) for o in run_reply['outputs']]
    )

    try:
      with Status("Creating url"):
        id = client.create_cell({
          "id": generate(size=11),
          "executeRequest": run_request,
          "executeReply": run_reply,
        })
    except Exception as err:
      print(err, file=sys.stderr)
      return

    io()
    display(CellLink(id))

get_ipython().register_magics(ShareMagic)
