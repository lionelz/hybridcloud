import time

from oslo.config import cfg

from nova import image
from nova.openstack.common import log as logging

from nova_driver.virt.hybrid.common import abstract_driver

CONF = cfg.CONF


LOG = logging.getLogger(__name__)


IMAGE_API = image.API()


class AWSDriver(abstract_driver.AbstractHybridNovaDriver):
    """The AWS Hybrid NOVA driver."""

    def __init__(self, virtapi, scheme="https"):
        super(AWSDriver, self).__init__(virtapi)

    def spawn(self,
              context,
              instance,
              image_meta,
              injected_files,
              admin_password,
              network_info=None,
              block_device_info=None):
        LOG.info('begin time of aws create vm is %s' %
                  (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))

        conversion_dir = super(AWSDriver, self).spawn(
            context,
            instance,
            image_meta,
            injected_files,
            admin_password,
            network_info,
            block_device_info
        )
        
        # convert to vmdk
        
        # post to s3
        
        # launch the VM with 2 networks
        
        
