import os
import requests
import uuid

from hyperagent.agent import lxd_driver
from hyperagent.common.container_image import container_image


class container_image_http(container_image):

    def __init__(self, uri):
        super(container_image_http, self).__init__(uri)
        # uri = 'http://images.linuxcontainers.org/images/gentoo/'
        # 'current/amd64/default/20160111_14:12/lxd.tar.xz'
        self._uri = uri
        self.lxd = lxd_driver.API()
        self._image_alias = 'my-image'

    def defined(self):
        return self.lxd.image_defined(self._image_alias)

    def upload(self):
        # set the image in a temporary folder
        file_dest = '/tmp/%s' % str(uuid.uuid4())
        response = requests.get(self._uri, stream=True)
        try:
            # download the file
            with open(file_dest, "wb") as f:
                for data in response.iter_content():
                    f.write(data)
            # set the alias name
            headers = {'alias': self._image_alias}
            self.lxd.image_upload(path=file_dest, headers=headers)
        finally:
            # remove the temporary image
            os.remove(file_dest)
        return True

    @property
    def alias(self):
        return self._image_alias
