"""
:mod:`hybrid` -- Hybrid vcloud nova support.
"""

from nova_driver.virt.hybrid.vcloud import vcloud_driver
from nova_driver.virt.hybrid.aws import aws_driver

from oslo_config import cfg

# TODO HybridDriver that change the value according to the type
VCloudDriver = vcloud_driver.VCloudDriver
AWSDriver = aws_driver.AWSDriver

if cfg.CONF.hybrid_driver.provider == 'vcloud':
    HybridDriver = VCloudDriver

if cfg.CONF.hybrid_driver.provider == 'aws':
    HybridDriver = AWSDriver
