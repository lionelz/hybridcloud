import os
import time

from nova import image

from nova.compute import hv_type

from oslo_config import cfg

from oslo_log import log as logging

from nova_driver.virt.hybrid.aws import aws_client
from nova_driver.virt.hybrid.common import abstract_driver
from nova_driver.virt.hybrid.common import image_convertor

LOG = logging.getLogger(__name__)


IMAGE_API = image.API()


class FakeDriver(abstract_driver.AbstractHybridNovaDriver):
    """A Fake NOVA driver."""

    def __init__(self, virtapi, scheme="https"):
        super(FakeDriver, self).__init__(virtapi)

    def spawn(self,
              context,
              instance,
              image_meta,
              injected_files,
              admin_password,
              network_info=None,
              block_device_info=None):
        LOG.info('begin time of fake create vm is %s' %
                 (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
        self.plug_vifs(context, instance, network_info,
                       '192.168.122.180', '192.168.122.180')

        LOG.info('end time of fake create vm is %s' %
                 (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))

    def get_available_nodes(self, refresh=False):
        return ['fake']
