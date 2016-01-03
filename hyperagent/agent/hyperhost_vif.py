#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo.config import cfg
from hyperagent.agent import hyper_agent_utils as hu
from hyperagent.agent import hypervm_vif
from hyperagent.agent import vm_namespace

from nova.openstack.common import lockutils
from nova.openstack.common import log as logging
from pylxd import api

hyper_host_opts = [
    cfg.StrOpt('container_image',
               default='local://?alias=trusty',
               help='Container image uri'),
    cfg.StrOpt('translation_bridge',
               default='br-trans',
               help='The Translation bridge name'),
    cfg.StrOpt('network_interface',
               default='eth1',
               help='The network interface for VM connection'),
    cfg.StrOpt('network_cidr',
               default='10.0.20.122/24',
               help='The inet v4 address'),
    cfg.StrOpt('default_gw',
               default='10.0.20.1',
               help='The default gateway'),
    ]


cfg.CONF.register_opts(hyper_host_opts, 'hyperagent')


LOG = logging.getLogger(__name__)

class HyperHostVIFDriver(hyper_vif_driver.HyperVMVIFDriver):
    """VIF driver for hyperhost networking."""
    
    def __init__(self, instance_id=None, call_back=None):
        super(HyperNodeVIFDriver, self).__init__()
        self.lxd = api.API()

    def startup_init(self):
        self.container_init()
        super.startup_init()
        self.lxd.start(self.instance_id,100)

    @lockutils.synchronized('hypernode-plug-unplug')
    def plug(self, instance_id, hyper_vif, provider_vif):
        LOG.debug("hyper_vif=%s" % hyper_vif)
        LOG.debug("provider_vif=%s" % provider_vif)
        vnic_veth = self.create_br_vnic(instance_id, hyper_vif)
        #set mac address on device
        hu.execute('ip', 'link', 'set', vnic_veth,
                           'address', hyper_vif['address'],
                           run_as_root=True)
        # set MTU
        hu.set_device_mtu(vnic_veth, 1400)
        container_nic_name = self._container_device_name( hyper_vif )
        eth_vif_config = {'devices': 
                            { container_nic_name:
                                { 'type':'nic',
                                  'nictype': 'physical',
                                  'parent': vnic_veth  
                                }
                            }
                         }
        self.lxd.container_update( instance_id, eth_vif_config )
        

    @lockutils.synchronized('hypernode-plug-unplug')
    def unplug(self, hyper_vif):
        self.driverImpl.unplug(hyper_vif)

    def container_init(self):
        null_profile = { 'config':{}, 'name': 'null_profile'}
        self.lxd.profile_create( null_profile )
        container_info = self.get_container_info()
        container_name = self.instance_id
        container_alias = container_info['alias']
        container_config = { 'name': container_name, 'profiles': 'null_profile',
                             'source': { 'type': image, 'alias':container_alias } } 
        self.lxd.container_init( container_config)

    def get_container_info(self):
        return {'alias':'trusty'}

    def _container_device_name( self, hyper_vif ):
        return 'eth0'
