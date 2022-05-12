import sys
from IPython.utils.capture import RichOutput

class CapturedIO(object):

  def __init__(self, stdout, stderr, traceback, outputs=None):
    self._stdout = stdout or ''
    self._stderr = stderr or ''
    self._traceback = traceback or ''
    self._outputs = outputs or []

  def __str__(self):
    return self._stdout

  @property
  def outputs(self):
    return [ RichOutput(**kargs) for kargs in self._outputs ]

  def show(self):
    """write my output to sys.stdout/err as appropriate"""
    sys.stdout.write(self._stdout)
    sys.stderr.write(self._stderr)
    sys.stderr.write('\n'.join(self._traceback))
    sys.stdout.flush()
    sys.stderr.flush()
    for kargs in self._outputs:
      RichOutput(**kargs).display()

  __call__ = show
