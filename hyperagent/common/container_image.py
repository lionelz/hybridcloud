from hyperagent.common import lxd_driver

from hyperagent.common.img_downloader import get_downloader as dwn


class container_image(object):

    def __init__(self, image_uri, rootfs_uri=None):
        self._image_uri = image_uri
        self._rootfs_uri = rootfs_uri
        self.lxd = lxd_driver.API()
        self._image_alias = 'my-image'

    def _defined(self):
        return self.lxd.image_defined(self._image_alias)

    def upload(self):
        if self._defined():
            return False

        with dwn(self._image_uri) as img_d, dwn(self._rootfs_uri) as rootfs_d:
            self.lxd.image_upload(path=img_d.get_file_dest(),
                                  rootfs=rootfs_d.get_file_dest(),
                                  alias=self._image_alias)
        return True

    @property
    def alias(self):
        return self._image_alias
