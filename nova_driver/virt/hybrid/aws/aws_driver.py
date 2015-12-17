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

