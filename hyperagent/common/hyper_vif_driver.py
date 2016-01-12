
import abc
import six


@six.add_metaclass(abc.ABCMeta)
class HyperVIFDriver(object):

    @abc.abstractmethod
    def startup_init(self):
        pass

    @abc.abstractmethod
    def cleanup(self):
        pass

    @abc.abstractmethod
    def plug(self, instance_id, hyper_vif, provider_vif):
        pass

    @abc.abstractmethod
    def unplug(self, hyper_vif):
        pass
