from time import sleep

def poll(step, target):
  while True:
    val = target()
    if bool(val):
      return val
    sleep(step)
