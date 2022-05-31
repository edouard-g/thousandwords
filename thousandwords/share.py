from IPython.core.magic import cell_magic, magics_class
from IPython import get_ipython
from thousandwords.publish import PublishMagic

@magics_class
class ShareMagic(PublishMagic):
  """ Alias for %%publish """

  @cell_magic("share")
  def cmagic(self, line="", cell=""):
    print("""Warning: '%%share' is deprecated. Use '%%publish --public' instead.""")
    super().publish(cell, public=True)

get_ipython().register_magics(ShareMagic)
