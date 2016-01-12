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


from hyperagent.agent import hyper_agent_utils as hu
from hyperagent.common import hyper_vif_driver

from nova.openstack.common import lockutils
from nova.openstack.common import log as logging


LOG = logging.getLogger(__name__)
NIC_NAME_LEN = 14


class HyperVMVIFDriver(hyper_vif_driver.HyperVIFDriver):
    """VIF driver for hypervm networking."""

    def __init__(self, instance_id=None, call_back=None):
        self.call_back = call_back
        self.instance_id = instance_id
        super(HyperVMVIFDriver, self).__init__()

    def startup_init(self):
        vifs_for_inst = self.call_back.get_vifs_for_instance(self.instance_id)
        net_info = vifs_for_inst.get('net_info')
        provider_net_info = vifs_for_inst.get('provider_net_info')
        for vif, provider_vif in zip(net_info, provider_net_info):
            self.plug(self.instance_id, vif, provider_vif)

    def cleanup(self):
        # nothing to do
        pass

    def get_br_name(self, iface_id):
        return ("qbr" + iface_id)[:NIC_NAME_LEN]

    def get_veth_pair_names(self, iface_id):
        return (("qvm%s" % iface_id)[:NIC_NAME_LEN],
                ("qvo%s" % iface_id)[:NIC_NAME_LEN])

    def get_veth_pair_names2(self, iface_id):
        return (("tap%s" % iface_id)[:NIC_NAME_LEN],
                ("tvo%s" % iface_id)[:NIC_NAME_LEN])

    def get_bridge_name(self, vif):
        br_int = vif['network']['bridge']
        if br_int:
            return br_int
        return 'br-int'

    def get_ovs_interfaceid(self, vif):
        return vif.get('ovs_interfaceid') or vif.get('id')

    def create_br_vnic(self, instance_id, vif):
        br_name = self.get_br_name(vif.get('id'))
        br_int_veth, qbr_veth = self.get_veth_pair_names(vif.get('id'))
        tap_veth, vnic_veth = self.get_veth_pair_names2(vif.get('id'))
        iface_id = self.get_ovs_interfaceid(vif)

        # linux bridge creation
        if not hu.device_exists(br_name):
            hu.execute('brctl', 'addbr', br_name,
                       run_as_root=True)
            hu.execute('brctl', 'setfd', br_name, 0,
                       run_as_root=True)
            hu.execute('brctl', 'stp', br_name, 'off',
                       run_as_root=True)

        # veth for br-int creation
        if not hu.device_exists(qbr_veth):
            hu.create_veth_pair(br_int_veth, qbr_veth)
            hu.execute('ip', 'link', 'set', br_name, 'up',
                       run_as_root=True)
            hu.execute('brctl', 'addif', br_name, br_int_veth,
                       run_as_root=True)

        # add in br-int the veth
        hu.create_ovs_vif_port(self.get_bridge_name(vif),
                               qbr_veth, iface_id,
                               vif['address'], instance_id)

        # veth for virtual nic creation
        if not hu.device_exists(vnic_veth):
            hu.create_veth_pair(tap_veth, vnic_veth)
            hu.execute('ip', 'link', 'set', br_name, 'up', run_as_root=True)
            hu.execute('brctl', 'addif', br_name, tap_veth, run_as_root=True)

        return vnic_veth

    def remove_br_vnic(self, vif):
        v1_name, v2_name = self.get_veth_pair_names(vif.get('id'))
        t1_name, t2_name = self.get_veth_pair_names2(vif.get('id'))

        # remove the br-int ports
        hu.delete_ovs_vif_port(self.get_bridge_name(vif), v2_name)

        # remove veths
        hu.delete_net_dev(v1_name)
        hu.delete_net_dev(v2_name)
        hu.delete_net_dev(t1_name)
        hu.delete_net_dev(t2_name)

        # remove linux bridge
        br_name = self.get_br_name(vif.get('id'))
        hu.execute('ip', 'link', 'set', br_name, 'down', check_exit_code=False,
                   run_as_root=True)
        hu.execute('brctl', 'delbr', br_name, check_exit_code=False,
                   run_as_root=True)

    @lockutils.synchronized('hypervm-plug-unplug')
    def plug(self, instance_id, hyper_vif, provider_vif):
        LOG.debug("hyper_vif=%s" % hyper_vif)
        LOG.debug("provider_vif=%s" % provider_vif)
        vnic_veth = self.create_br_vnic(instance_id, hyper_vif)
        for subnet in hyper_vif['network']['subnets']:
            LOG.debug("subnet: %s" % subnet)
            if subnet['version'] == 4:
                # set the IP/mac on the vnic
                h_cidr = subnet['cidr']
                h_ip = subnet['ips'][0]['address']
                h_cidr_ip = h_ip + '/' + h_cidr.split('/')[1]
                hu.execute('ip', 'addr', 'add', h_cidr_ip,
                           'dev', vnic_veth,
                           check_exit_code=False,
                           run_as_root=True)
                hu.execute('ip', 'link', 'set', vnic_veth,
                           'address', hyper_vif['address'],
                           run_as_root=True)
                # set the default route
                h_gw = None
                if subnet.get('gateway'):
                    h_gw = subnet['gateway'].get('address')
                    if h_gw:
                        # TODO: how to choose the good gateway????
                        # remove default route
                        hu.execute('ip', 'route', 'del', '0/0')
                        hu.execute('route', 'add', 'default', 'gw', h_gw)
        # set MTU
        hu.set_device_mtu(vnic_veth, 1400)

    @lockutils.synchronized('hypervm-plug-unplug')
    def unplug(self, hyper_vif):
        LOG.debug("unplug=%s" % hyper_vif)
        self.remove_br_vnic(hyper_vif)
