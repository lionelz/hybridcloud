import abc

from nova.openstack.common import log as logging
from oslo.config import cfg


LOG = logging.getLogger(__name__)
CONF = cfg.CONF

class ProviderClient(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self):
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

