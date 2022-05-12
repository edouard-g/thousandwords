from pyflakes.api import check
from pyflakes.reporter import Reporter as PyfReporter
from pyflakes.messages import UndefinedName
from io import StringIO

class Reporter(PyfReporter):
  def __init__(self):
    self.undefined = []

  def unexpectedError(self, filename, msg):
    self._stderr = StringIO()
    super().unexpectedError(filename, msg)
    raise Exception(self._stderr.getvalue()) from None

  def syntaxError(self, filename, msg, lineno, offset, text):
    self._stderr = StringIO()
    super().syntaxError(filename, msg, lineno, offset, text)
    raise Exception(self._stderr.getvalue()) from None

  def flake(self, message):
    if (isinstance(message, UndefinedName)):
      self.undefined.append(message)

def resolveUndefined(code):
  reporter = Reporter()
  check(code, "<cell>", reporter)
  return reporter.undefined
