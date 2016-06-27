import abc
import six


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

    @abc.abstractmethod
    def get_net_conf(self, instance, net_list, name):
        pass
