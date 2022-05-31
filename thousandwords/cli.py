import sys
import argparse
import logging
import json
from .config import CONFIG
from .auth import CognitoAuth
from .client import Client

logger = logging.getLogger("thousandwords.cli")

def login(args) -> None:
  instance = args.instance
  try:
    curr_instance = CONFIG.instance
  except:
    curr_instance = None
  while not instance:
    prompt = "1000words instance URL [%s]: " % (
      curr_instance or "e.g.: 1000words-hq.com"
    )
    instance = input(prompt).strip()
    if not instance:
      instance = curr_instance

  CONFIG.instance = instance
  CONFIG.save(update_default_instance=True)

  auth = CognitoAuth()
  auth.fetch_new_tokens()
  print("Authentication successful.")

def cells_create(args):
  with open(args.file) as f:
    input = json.load(f)
  id = Client().create_cell(input)
  print(f"Successfully created cell {id}")

def cells_run(args):
  with open(args.file) as f:
    req = json.load(f)
  resp = Client().run_cell(req)
  print(f"Successfully ran cell: {resp}")

def storage_upload(args):
  with open(args.file) as f:
    key = f'uploads/{args.key}'
    Client().upload(key, f.read())
  print(f"Successfully created object with key: {key}")

def storage_get(args):
  object = Client().get(args.key)
  print(f"Value: {object.decode('utf-8')}")

STORAGE_COMMANDS = [
  {
    "name": "upload",
    "help": "upload value in store",
    "handler": storage_upload
  },
  {
    "name": "get",
    "help": "retrieve value from store",
    "handler": storage_get
  }
]

CELLS_COMMANDS = [
  {
    "name": "create",
    "help": "create cell",
    "handler": cells_create,
  },
  {
    "name": "run",
    "help": "run cell",
    "handler": cells_run,
  }
]

COMMANDS = [
  {
    "name": "login",
    "help": "authenticate thousandwords cli",
    "handler": login,
  },
  {
    "name": "cells",
    "help": "run `thousandwords cells -h` for subcommands",
    "subcommands": CELLS_COMMANDS,
  },
  {
    "name": "storage",
    "help": "run `thousandwords storage -h` for subcommands",
    "subcommands": STORAGE_COMMANDS,
  }
]

def main():
  parser = argparse.ArgumentParser(
    description="1000words command line interface.",
  )
  parser.add_argument(
    "-v", "--verbose", action="store_true", help="run in verbose mode"
  )

  parser.add_argument("--debug", action="store_true", help="run in debug mode")

  parser.add_argument("--instance", metavar="URL", help="1000words instance url")

  cmd_parsers = parser.add_subparsers(
    title="commands", metavar="CMD", help="run `thousandwords CMD -h` for command help"
  )

  for cmd in sorted(COMMANDS, key=lambda c: c["name"]):
    p = cmd_parsers.add_parser(
      cmd["name"],
      help=cmd["help"],
      description=None if cmd.get("subcommands") else cmd["help"],
    )
    if "handler" in cmd:
      p.set_defaults(handler=cmd["handler"])

    if "subcommands" in cmd:
      subcmd_parsers = p.add_subparsers(
        title="commands",
        metavar="CMD",
        help=f"run `thousandwords {cmd['name']} CMD -h for subcommand help",
      )
      for subcmd in sorted(cmd["subcommands"], key=lambda c: c["name"]):
        p = subcmd_parsers.add_parser(
          subcmd["name"], help=subcmd["help"], description=subcmd["help"]
        )
        p.set_defaults(handler=subcmd["handler"])

        if cmd["name"] == "cells":
          if subcmd["name"] == "create":
            p.add_argument(
              "file",
              help="file with cell data in JSON format",
            )
          if subcmd["name"] == "run":
            p.add_argument(
              "file",
              help="file with request data in JSON format",
            )
        if cmd["name"] == "storage":
          p.add_argument("key", help='object key')
          if subcmd["name"] == "upload":
            p.add_argument("file", help="file with data for object")

  args = parser.parse_args()

  log_level = logging.WARNING
  if args.verbose:
    log_level = logging.INFO

  if args.debug:
    log_level = logging.DEBUG

  logging.basicConfig(
    level=log_level,
    stream=sys.stderr,
    format="%(levelname)s | %(asctime)s | %(name)s | %(message)s",
  )

  if args.instance:
    CONFIG.instance = args.instance

  if hasattr(args, "handler"):
    try:
      args.handler(args)
    except Exception as e:
      if args.debug:
        raise e
      print(e)
      sys.exit(1)
  else:
    parser.print_help()

if __name__ == "__main__":
  main()
