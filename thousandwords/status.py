import sys

class Status:
  def __init__(self, text):
    self.text = text

  def __enter__(self):
    print(f'thousandwords:{self.text}', end='')
    sys.stdout.flush()
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    if exc_value is not None:
      print(' [Failure]')
    else:
      print(' [Success]')
    sys.stdout.flush()
    return False
