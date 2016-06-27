"""
:mod:`hybrid` -- Hybrid vcloud nova support.
"""

from oslo_config import cfg
from nova_driver.virt.hybrid.common import abstract_driver


if cfg.CONF.hybrid_driver.provider == 'vcloud':
    from nova_driver.virt.hybrid.vcloud import vcloud_driver
    VCloudDriver = vcloud_driver.VCloudDriver
    HybridDriver = VCloudDriver

if cfg.CONF.hybrid_driver.provider == 'aws':
    from nova_driver.virt.hybrid.aws import aws_driver
    AWSDriver = aws_driver.AWSDriver
    HybridDriver = AWSDriver
