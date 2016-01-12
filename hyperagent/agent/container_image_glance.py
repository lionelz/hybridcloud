import os
import urlparse

from glanceclient import client

from hyperagent.agent import lxd_driver
from hyperagent.common.container_image import container_image

from keystoneclient import session
from keystoneclient.auth.identity import v2 as v2_auth

from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)

class container_image_glance(container_image):

    def __init__(self, uri):
        super(container_image_glance, self).__init__(uri)
        # uri = 'glance://demo:stack@192.168.10.247:9292/?scheme=http'
        # '&image_uuid=2269180b-a9b1-44d0-93ae-baaacdd0114a'
        # '&project_name=demo'
        # '&auth_url=http://192.168.10.247:5000/v2.0')
        self._uri = uri
        self._url = urlparse.urlparse(uri)
        self._params = urlparse.parse_qs(self._url.query)
        self.lxd = lxd_driver.API()
        self._image_uuid = self._params['image_uuid'][0]
        self._image_alias = 'i%s' % self._image_uuid

    def defined(self):
        return self.lxd.image_defined(self._image_alias)

    def upload(self):
        # set the image in a temporary folder
        file_dest = '/tmp/%s' % self._image_alias
        endpoint = '%s://%s:%s/v2' % (self._params['scheme'][0],
                                      self._url.hostname,
                                      self._url.port)
        # keystone login
        auth = v2_auth.Password(
            auth_url=self._params['auth_url'][0],
            username=self._url.username,
            password=self._url.password,
            tenant_name=self._params['project_name'][0]
        )
        token = session.Session(auth).get_token()

        # glance client
        glance_client = client.Client(2,
                                      endpoint=endpoint,
                                      token=token)
        try:
            # download the file
            with open(file_dest, 'wb') as f:
                for chunk in glance_client.images.data(self._image_uuid):
                    f.write(chunk)
            # set the alias name
            headers = {'alias': self._image_alias}
            self.lxd.image_upload(path=file_dest, headers=headers)
        finally:
            # remove the temporary image
            os.remove(file_dest)

    @property
    def alias(self):
        return self._image_alias
