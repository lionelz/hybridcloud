import urlparse
from hyperagent.agent import lxd_driver
from hyperagent.common.container_image import container_image


class container_image_local(container_image):

    def __init__(self, uri):
        super(container_image_local, self).__init__(uri)
        # uri = 'local://trusty'
        self._uri = uri
        self.lxd = lxd_driver.API()
        self._image_alias = urlparse.urlparse(uri)['netloc']

    def defined(self):
        return self.lxd.image_defined(self._image_alias)

    def upload(self):
        return False

    @property
    def alias(self):
        return self._image_alias
