from cProfile import run
import json
import uuid
import sys
from posixpath import join as urljoin
from urllib.parse import quote
import webbrowser
from time import time
from base64 import b64decode
import struct
from types import ModuleType
import secrets
import click
from IPython import get_ipython
from IPython.display import display
from IPython.core.magic import (
  Magics,
  cell_magic,
  magics_class,
)
from IPython.core import magic_arguments
from IPython.core.error import StdinNotImplementedError
from IPython.utils.capture import capture_output
from nanoid import generate
from thousandwords.auth import CognitoAuth
from thousandwords.cli import login
from thousandwords_core.serializer import Serializer
from .status import Status
from .lint import resolveUndefined
from .client import Client
from .capture import CapturedIO
from .config import CONFIG
from .polling import poll
from . import __version__

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

def size_for_png(data):
  check = struct.unpack('>i', data[4:8])[0]
  if check != 0x0d0a1a0a:
    return
  return struct.unpack('>ii', data[16:24])

def get_title(lines):
  for l in lines:
    if len(l) > 0:
      if l.startswith('#'):
        l = l[1:]
      return l.strip()
  return 'New snippet'

class CellLink:
  def __init__(self, id):
    self.url = urljoin(CONFIG.instance_url, f'c/{id}')
  def _repr_pretty_(self, p, cycle):
    p.text('\n' + self.url)

@magics_class
class PublishMagic(Magics):
  def __init__(self, shell):
    Magics.__init__(self, shell=shell)

  @magic_arguments.magic_arguments()
  @magic_arguments.argument('--public', action='store_true',
    help="Publish publicly to an unlisted URL. Anyone with the link can view."
  )
  @magic_arguments.argument("--no-variables", action="store_true", 
    help="""Don't include the variables required for execution in the publication"""
  )
  @magic_arguments.argument("--with-variables", action="store_true", 
    help="""Include the variables required for execution in the publication"""
  )
  @magic_arguments.argument("--not-runnable", action="store_true", 
    help="""Don't make the publication runnable. 
    
    If set, the cell is run locally and only the code and outputs are captured"""
  )
  @cell_magic("publish")
  def cmagic(self, line="", cell=""):
    args = magic_arguments.parse_argstring(self.cmagic, line)
    self.publish(cell, **vars(args))
  
  def publish(self, cell, public=False, no_variables=False, with_variables=False, not_runnable=False):
    lines = cell.split('\n')
    try:
      undefs = resolveUndefined(cell)
    except Exception as e:
      print(e, file=sys.stderr)
      return
    vnames = sorted(list(set([u.message_args[0] for u in undefs])))

    if not_runnable and with_variables:
      print("--not-runnable and --with-variables are mutually exclusive. Pick at most one.")
      return

    client = Client()
    puts3_tasks = []
    def puts3(key, name, data):
      with Status(f"Uploading dependency '{name}'"):
        client.upload(key, data)
    def schedule_puts3(name, data):
      key = f'uploads/{str(uuid.uuid4())}'
      puts3_tasks.append(lambda: puts3(key, name, data))
      return key
    srz = Serializer(schedule_puts3)
    prompt_variables = []
    should_run_remote = True
    if not_runnable:
      should_run_remote = False
    else:
      for vname in vnames:
        try:
          obj = self.shell.user_ns[vname]
        except KeyError:
          print(f"Dependency '{vname}' is not defined", file=sys.stderr)
          return
        if not isinstance(obj, ModuleType):
          if no_variables:
            should_run_remote = False
            break
          elif not with_variables:
            prompt_variables.append(vname)
        try:
          srz.add(vname, obj)
        except Exception as err:
          print(f"Could not serialize {vname}: {err}", file=sys.stderr)
          return

    if should_run_remote and len(prompt_variables) > 0:
      varstr = ', '.join([f"'{v}'" for v in sorted(prompt_variables)])
      plur = 's' if len(vnames) > 1 else ''
      question = f"Do you want to include variable{plur} {varstr} in your publication and make it runnable ? (y/[N])"
      try:
        should_run_remote = self.shell.ask_yes_no(question, default='n')
      except StdinNotImplementedError:
        should_run_remote = False
      
    if should_run_remote:
      for task in puts3_tasks:
        task()
      run_request = {
        "lines": add_dependency_injection_comment(vnames, lines), 
        "userNS": srz.ns, 
        "version": get_version(),
        "clientVersion": f'py-{__version__}'
      }
      try:
        with Status("Executing cell remotely"):
          run_reply = client.run_cell(run_request)
      except Exception as err:
        print(err, file=sys.stderr)
        return
      if len(run_reply['userNS']) > 0:
        vnames = [v['name'] for v in run_reply['userNS']]
        print(f"Variable{'s' if len(vnames) > 1 else ''} captured: {', '.join(vnames)}")
    else:
      with capture_output() as io:
        self.shell.run_cell(cell)
      run_request = {"lines": lines, "version": 'local'}
      outputs = []
      for o in io.outputs:
        reprs = []
        for mime, data in o.data.items():
          if mime == 'image/png':
            data = b64decode(data)
            w, h = size_for_png(data)
            with Status(f"Uploading {mime} output"):
              key = f'public/{generate(size=11)}.png'
              client.upload(key, data)
            reprs.append({"mime": mime, "key": key, "width": w, "height": h})
          else:
            reprs.append({"mime": mime, "data": data})
        outputs.append({"metadata": json.dumps(o.metadata), "representations": reprs})
      run_reply = {"stdout": io.stdout, "stderr": io.stderr, "outputs": outputs}

    token = str(secrets.randbits(64))
    try:
      idc = client.create_cell({
        "id": generate(size=11),
        "isPublic": public,
        "title": get_title(lines),
        "executeRequest": run_request,
        "executeReply": run_reply,
        "token": token,
        "ttl": None if public else int(time()) + 10 * 60
      })
    except Exception as err:
      print(f'Create cell failed: {err}', file=sys.stderr)
      return
    try:
      idi = client.create_invite({
        "token": token,
        "cellId": idc,
        "mode": "owner",
        "counter": 1,
      })
    except Exception as err:
      print(f'Create invite failed: {err}', file=sys.stderr)
      return
    
    cell_url = urljoin(CONFIG.instance_url, f'c/{idc}')
    if public:
      join_url = urljoin(CONFIG.instance_url, f'join/{idi}')
      print('\nPrivate — do not share — Use this URL to update or delete your publication:\n'
        + join_url)
      print('\nUse this URL to share:\n' + cell_url)
    else:
      try:
        webbrowser.get()
        has_browser = True
      except:
        has_browser = False
      callback = generate()
      join_url = urljoin(CONFIG.instance_url, f'join/{idi}?callback={quote(callback)}&share=1')
      if has_browser:
        click.launch(join_url)
      else:
        print('\nGo to this URL to finalize your publication:\n' + join_url)
      
      poll(4, lambda: client.get_callback(callback) == callback)
      print('\nUse this URL to share:\n' + cell_url)


get_ipython().register_magics(PublishMagic)
