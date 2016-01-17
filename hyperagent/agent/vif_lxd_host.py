import base64

from oslo.config import cfg

from hyperagent.agent import vif_agent

from hyperagent.common import hyper_agent_utils as hu
from hyperagent.common import lxd_driver

from hyperagent.common.container_image import container_image

from nova.openstack.common import lockutils
from nova.openstack.common import log as logging

hyper_host_opts = [
    cfg.StrOpt('container_image_uri',
               default='local://my-image',
               help='Container image uri'),
    cfg.StrOpt('container_rootfs_uri',
               help='Container rootfs uri'),
    cfg.StrOpt('user_data',
               help='user data to inject to the container'),
    cfg.StrOpt('key_data',
               help='key data to inject to the container'),
]


cfg.CONF.register_opts(hyper_host_opts, 'hyperagent')

LOG = logging.getLogger(__name__)


class LXDHostVIFDriver(vif_agent.AgentVMVIFDriver):
    """VIF driver for hyper host networking."""

    def __init__(self, instance_id=None, call_back=None):
        super(LXDHostVIFDriver, self).__init__(instance_id, call_back)
        self.lxd = lxd_driver.API()
        self.nics = {}
        self.container_name = 'my-container'
        self.container_image_uri = cfg.CONF.hyperagent.container_image_uri
        self.container_rootfs_uri = cfg.CONF.hyperagent.container_rootfs_uri
        self.container_image = container_image(
            self.container_image_uri, self.container_rootfs_uri)

    def startup_init(self):
        # download the image
        if self.container_image.upload():
            self.container_init()
        if self.lxd.container_running(self.container_name):
            return
        # remove all eth config for the container
        self.lxd.container_update(self.container_name, {})
        super(LXDHostVIFDriver, self).startup_init()
        self.lxd.container_start(self.container_name, 100)

    @lockutils.synchronized('hyperhost-plug-unplug')
    def plug(self, instance_id, hyper_vif, provider_vif):
        LOG.debug("hyper_vif=%s" % hyper_vif)
        LOG.debug("provider_vif=%s" % provider_vif)
        vnic_veth = self.create_br_vnic(instance_id, hyper_vif)
        # set mac address on device
        hu.execute('ip', 'link', 'set', vnic_veth,
                   'address', hyper_vif['address'],
                   run_as_root=True)
        # set MTU
        hu.set_device_mtu(vnic_veth, 1400)
        container_nic_name = self._container_device_name(hyper_vif)
        eth_vif_config = {
            'devices': {
                container_nic_name: {
                    'type': 'nic',
                    'nictype': 'physical',
                    'parent': vnic_veth
                }
            }
        }

        self.lxd.container_update(self.container_name, eth_vif_config)

    @lockutils.synchronized('hyperhost-plug-unplug')
    def unplug(self, hyper_vif):
        keys_to_remove = [
            key
            for key, value in self.nics.iteritems()
            if value == hyper_vif['address']
        ]
        for key in keys_to_remove:
            del self.nics[key]
        self.driverImpl.unplug(hyper_vif)

    def container_init(self):
        null_profile = {
            'config': {},
            'name': 'null_profile'
        }
        self.lxd.profile_create(null_profile)
        container_info = self.get_container_info()
        container_alias = container_info['alias']
        container_config = {
            'name': self.container_name,
            'profiles': ['null_profile'],
            'source': {
                'type': 'image',
                'alias': container_alias
            }
        }
        self.lxd.container_init(container_config)
        # add the user data and the ssh key
        udata = cfg.CONF.hyperagent.user_data
        kdata = cfg.CONF.hyperagent.key_data
        s_config = {}
        if udata and udata != '':
            s_config['user.user-data'] = base64.b64decode(udata)
        if kdata and kdata != '':
            s_config['user.meta-data'] = (
                '#cloud-config\n\nssh_authorized_keys:\n  - %s\n') % kdata
        self.lxd.container_update(self.container_name, {'config': s_config})

    def get_container_info(self):
        return {'alias': self.container_image.alias}

    def _container_device_name(self, hyper_vif):
        index = 0
        if bool(self.nics) is True:
            index = max(self.nics.values())
            index += 1
        self.nics[index] = hyper_vif['address']
        return "eth%d" % index
