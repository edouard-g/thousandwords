from IPython import get_ipython
from thousandwords.share import ShareMagic
import textwrap
import pytest
from io import StringIO
from contextlib import redirect_stderr, redirect_stdout

""" Should be run from pyclient/run_tests.sh """

def runshare(ip, cell):
  cell = textwrap.dedent(cell)
  return ip.run_cell_magic("share", '', cell)

def runcell(ip, cell):
  cell = textwrap.dedent(cell)
  return ip.run_cell(cell)

@pytest.fixture
def ip():
  ip = get_ipython()
  ip.register_magics(ShareMagic(shell=ip))
  return ip

def test_syntax_error(ip):
  with redirect_stderr(StringIO()) as err:
    res = runshare(ip, 'gibberish aksldf ;lkj asd')
  assert 'aksldf' in err.getvalue()
  assert res is None

def test_dependency_not_defined(ip):
  with redirect_stderr(StringIO()) as err:
    res = runshare(ip, 'x = myvar_y + 1')
  assert 'myvar_y' in err.getvalue()
  assert 'not defined' in err.getvalue()
  assert res is None

def test_unpicklable(ip):
  runcell(ip, '''
    class Unpicklable:
      def __reduce__(self):
        raise Exception("not picklable")
    global exit
    my_unpicklable = Unpicklable()
  ''')
  with redirect_stderr(StringIO()) as err:
    res = runshare(ip, 'print(my_unpicklable)')
  assert 'my_unpicklable' in err.getvalue()
  assert 'not picklable' in err.getvalue()
  assert res is None

def test_dependency_injection(ip):
  runcell(ip, '''
    import pandas as pd
    from sklearn import datasets
    iris = datasets.load_iris(as_frame=True).data
    incr = lambda x: x + 1
    x = 100
    mystr = 'toto'
    myfloat = 3.2
  ''')
  out = StringIO()
  with redirect_stdout(out):
    runshare(ip, '''
      mystr = mystr * 2
      y = x * 2
      mydesc = iris.describe()
      ser = pd.Series([1, 2, 3, 4, 5])
      z = incr(10)
      z2 = myfloat + 1
      digits = datasets.load_digits(as_frame=True).data
      print("--START--")
      print(f"{mystr}-{x}-{y}-{len(mydesc)}-{ser.sum()}-{z}-{z2}-{len(digits)}")
      print("--STOP--")
    ''')
  assert out.getvalue().split("--START--")[1].strip().split("--STOP--")[0].strip() == 'totototo-100-200-8-15-11-4.2-1797'

def test_dedupe_dependencies(ip):
  runcell(ip, "xyx = 'toto' * 250")
  out = StringIO()
  with redirect_stdout(out):
    runshare(ip, '''
      z = xyx + xyx + xyx + xyx + xyx
    ''')
  assert out.getvalue().count("Uploading dependency 'xyx'") == 1
