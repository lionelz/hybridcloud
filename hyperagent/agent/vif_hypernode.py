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
from hyperagent.agent import vif_agent

from nova.openstack.common import lockutils
from nova.openstack.common import log as logging

hyper_node_agent_opts = [
    cfg.StrOpt('network_mngt_interface',
               default='eth0',
               help='The management network interface'),
    cfg.StrOpt('network_data_interface',
               default='eth1',
               help='The data network interface'),
    cfg.StrOpt('network_vm_interface',
               default='eth1',
               help='The VM network interface'),
    ]


cfg.CONF.register_opts(hyper_node_agent_opts, 'hyperagent')


LOG = logging.getLogger(__name__)
NIC_NAME_LEN = vif_agent.NIC_NAME_LEN


class HyperNodeVIFDriver(vif_agent.AgentVMVIFDriver):
    """VIF driver for hypernode networking."""

    def __init__(self, instance_id=None, call_back=None):
        super(HyperNodeVIFDriver, self).__init__()
        self.vm_nic = cfg.CONF.hyperagent.network_vm_interface

    def startup_init(self):
        vifs_for_inst = self.call_back.get_vifs_for_hyper_node(
            self.instance_id)
        hyper_net_info = vifs_for_inst.get('hyper_net_info')
        provider_net_info = vifs_for_inst.get('provider_net_info')
        for hyper_vif, provider_vif in zip(hyper_net_info, provider_net_info):
            self.plug(self.instance_id, hyper_vif, provider_vif)

    def cleanup(self):
        pass

    def get_port_id(self, port_name):
        show_res = hu.execute('ovs-ofctl',
                              'show',
                              self.br_trans,
                              run_as_root=True)[0]
        for s in show_res.split():
            if port_name in s:
                return s.split('(')[0]
        return None

    def get_vif_devname(self, vif):
        if 'devname' in vif:
            return vif['devname']
        return ("nic" + vif.get('id'))[:NIC_NAME_LEN]

    def get_vif_devname_with_prefix(self, vif, prefix):
        devname = self.get_vif_devname(vif)
        return prefix + devname[3:]

    def get_veth_pair_names3(self, iface_id):
        return (("rvb%s" % iface_id)[:NIC_NAME_LEN],
                ("rvo%s" % iface_id)[:NIC_NAME_LEN])

    @lockutils.synchronized('hypernode-plug-unplug')
    def plug(self, instance_id, hyper_vif, provider_vif):
        LOG.debug("hyper_vif=%s" % hyper_vif)
        LOG.debug("provider_vif=%s" % provider_vif)
        # provider_ip = provider_vif.get('ip')
        # h_ns_veth = self.create_br_vnic(instance_id, hyper_vif)

    @lockutils.synchronized('hypernode-plug-unplug')
    def unplug(self, hyper_vif):
        self.remove_br_vnic(hyper_vif)
        r1_name, r2_name = self.get_veth_pair_names3(hyper_vif.get('id'))
        tvo_port = self.get_port_id(r1_name)
        vm_namespace = self.get_namespace(hyper_vif.get('id'))

        # remove the br-trans ports
        hu.delete_ovs_vif_port(self.br_trans, r1_name)

        # remove veths
        hu.delete_net_dev(r1_name)
        hu.delete_net_dev(r2_name)

        # remove namespace
        hu.execute('ip', 'netns', 'delete', vm_namespace,
                   check_exit_code=False,
                   run_as_root=True)

        # remove the flows....
        hu.execute('ovs-ofctl', 'del-flows', self.br_trans,
                   'cookie=%(tvo_port)s/-1' % {'tvo_port': tvo_port},
                   check_exit_code=False,
                   run_as_root=True)
