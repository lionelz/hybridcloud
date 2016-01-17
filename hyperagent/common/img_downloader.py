import abc
import os
import requests
import six
import urlparse
import uuid

from glanceclient import client

from keystoneclient import session

from keystoneclient.auth.identity import v2 as v2_auth

from nova.openstack.common import importutils


def get_downloader(uri):
    if uri:
        url = urlparse.urlparse(uri)
        scheme = url.scheme
        cname = 'hyperagent.common.img_downloader.downloader_%s' % scheme
    else:
        cname = 'hyperagent.common.img_downloader.downloader_none'
    return importutils.import_object(cname, uri)


@six.add_metaclass(abc.ABCMeta)
class downloader(object):

    def __init__(self, uri):
        self._uri = uri

    def __enter__(self):
        self._file_dest = '/tmp/%s' % str(uuid.uuid4())
        self.download(self._file_dest)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if os.path.exists(self._file_dest):
            os.remove(self._file_dest)

    def get_file_dest(self):
        return self._file_dest

    @abc.abstractmethod
    def download(self, file_dest):
        pass


class downloader_none(downloader):

    def __init__(self, uri):
        super(downloader_none, self).__init__(uri)

    def download(self, file_name):
        pass


class downloader_http(downloader):

    def __init__(self, uri):
        super(downloader_http, self).__init__(uri)
        # uri = 'http://images.linuxcontainers.org/images/gentoo/'
        # 'current/amd64/default/20160111_14:12/lxd.tar.xz'


    def download(self, file_name):
        response = requests.get(self._uri, stream=True)
        # download the file
        with open(file_name, "wb") as f:
            for data in response.iter_content():
                f.write(data)


class downloader_https(downloader_http):
    pass


class downloader_glance(downloader):

    def __init__(self, uri):
        super(downloader_glance, self).__init__(uri)
        # uri = 'glance://demo:stack@192.168.10.247:9292/?scheme=http'
        # '&image_uuid=2269180b-a9b1-44d0-93ae-baaacdd0114a'
        # '&project_name=demo'
        # '&auth_url=http://192.168.10.247:5000/v2.0')
        self._url = urlparse.urlparse(uri)
        self._params = urlparse.parse_qs(self._url.query)
        self._image_uuid = self._params['image_uuid'][0]

    def download(self, file_name):
        # set the image in a temporary folder
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
        # download the file
        with open(file_name, 'wb') as f:
            for chunk in glance_client.images.data(self._image_uuid):
                f.write(chunk)
