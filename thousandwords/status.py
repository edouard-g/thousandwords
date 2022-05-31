import sys
import threading

class Writer:
  N = 42
  def __init__(self):
    self.lock = threading.Lock()
    self.cnt = 0

  def write(self, msg, finish=False):
    with self.lock:
      if finish:
        print(' ' * (self.N-self.cnt), end='')
      print(msg, end='')
      if finish:
        print()
      sys.stdout.flush()
      self.cnt = self.cnt + len(msg)

# https://stackoverflow.com/questions/3393612/run-certain-code-every-n-seconds
class RepeatedTimer(object):
  def __init__(self, interval, function, *args, **kwargs):
    self._timer     = None
    self.interval   = interval
    self.function   = function
    self.args       = args
    self.kwargs     = kwargs
    self.is_running = False
    self.start()

  def _run(self):
    self.is_running = False
    self.start()
    self.function(*self.args, **self.kwargs)

  def start(self):
    if not self.is_running:
      self._timer = threading.Timer(self.interval, self._run)
      self._timer.start()
      self.is_running = True

  def stop(self):
    self._timer.cancel()
    self.is_running = False

class Status:
  def __init__(self, text):
    self.text = text
    self.writer = Writer()

  def __enter__(self):
    self._timer = RepeatedTimer(1, self.writer.write, '.')
    self.writer.write(f'{self.text} ')
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    self._timer.stop()
    if exc_value is not None:
      self.writer.write('[Failure]', finish=True)
    else:
      self.writer.write('[Success]', finish=True)
    return False
