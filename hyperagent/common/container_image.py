

import abc
import six
import urlparse

from nova.openstack.common import importutils


def get_container_image(container_image_uri):
    url = urlparse.urlparse(container_image_uri)
    scheme = url.scheme
    cname = 'hyperagent.agent.container_image_%s.container_image_%s' % (
        scheme, scheme)
    return importutils.import_object(cname, container_image_uri)


@six.add_metaclass(abc.ABCMeta)
class container_image(object):

    def __init__(self, uri):
        self._uri = uri

    @abc.abstractmethod
    def defined(self):
        pass

    @abc.abstractmethod
    def upload(self):
        pass

    @abc.abstractproperty
    def alias(self):
        pass
