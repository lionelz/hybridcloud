import abc
import six

from nova.openstack.common import log as logging
from oslo.config import cfg


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


@six.add_metaclass(abc.ABCMeta)
class ProviderClient(object):

    def __init__(self):
        pass

    @abc.abstractmethod
    def get_vm_status(self, instance, name):
        pass

    @abc.abstractmethod
    def power_off(self, instance, name):
        pass

    @abc.abstractmethod
    def power_on(self, instance, name):
        pass

    @abc.abstractmethod
    def delete(self, instance, name):
        pass

    @abc.abstractmethod
    def reboot(self, instance, name):
        pass
