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

hyper_node_agent_opts = [
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


cfg.CONF.register_opts(hyper_node_agent_opts, 'hyperagent')


LOG = logging.getLogger(__name__)
NIC_NAME_LEN = hypervm_vif.NIC_NAME_LEN

class HyperNodeVIFDriver(hypervm_vif.HyperVMVIFDriver):
    """VIF driver for hypernode networking."""
    
    def __init__(self, instance_id=None, call_back=None):
        super(HyperNodeVIFDriver, self).__init__()
        self.br_trans = cfg.CONF.hyperagent.translation_bridge
        self.nic = cfg.CONF.hyperagent.network_interface
        self.cidr = cfg.CONF.hyperagent.network_cidr
        self.gw_ip = cfg.CONF.hyperagent.default_gw
        self.create_ovs_br()

    def startup_init(self):
        vifs_for_inst = self.call_back.get_vifs_for_hyper_node(self.instance_id)
        net_info = vifs_for_inst.get('net_info')
        provider_net_info = vifs_for_inst.get('provider_net_info')
        for vif, provider_vif in zip(net_info, provider_net_info):
            self.plug(self.instance_id, vif, provider_vif)

    def cleanup(self):
        hu.del_bridge(cfg.CONF.hyperagent.translation_bridge)

    def create_ovs_br(self):
        l_ip = self.cidr[0:self.cidr.find('/')]
        hu.ovs_vsctl(['--may-exist', 'add-br', self.br_trans])
        hu.execute('ovs-ofctl', 'del-flows', self.br_trans,
                   run_as_root=True)
        self.add_flow("priority=0,actions=normal")
        self.add_flow("priority=1000,dl_type=0x86dd,actions=drop")
        self.add_flow("priority=1000,dl_type=0x800,"
                      "nw_dst=%s,actions=normal" % l_ip)
        self.add_flow("priority=1000,dl_type=0x800,"
                      "nw_src=%s,actions=normal" % l_ip)
        self.add_flow("priority=1000,dl_type=0x806,"
                      "arp_tpa=%s,actions=normal" % l_ip)
        self.add_flow("priority=1000,dl_type=0x806,"
                      "arp_spa=%s,actions=normal" % l_ip)

        nic_mac = hu.get_mac(self.nic)
        hu.ovs_vsctl(['set', 'bridge', self.br_trans,
                      'other-config:hwaddr=%s' % nic_mac])
        hu.ovs_vsctl(['--may-exist', 'add-port',
                      self.br_trans, self.nic])
        hu.execute('ip', 'link', 'set', 'dev', self.br_trans, 'up',
                   run_as_root=True)
        hu.execute('ip', 'link', 'set', 'dev', self.nic, 'promisc',
                   'on', run_as_root=True)
        hu.execute('ip', 'addr', 'del', self.cidr,
                   'dev', self.nic,
                   check_exit_code=False,
                   run_as_root=True)
        hu.execute('ip', 'addr', 'add', self.cidr,
                   'dev', self.br_trans,
                   check_exit_code=False,
                   run_as_root=True)
        hu.execute('ip', 'route', 'add', 'default',
                   'via', self.gw_ip,
                   check_exit_code=False,
                   run_as_root=True)

    def add_flow(self, flow):
        hu.execute('ovs-ofctl', 'add-flow', self.br_trans,
                   flow, run_as_root=True)

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

    def _get_default_route_mac(self, retry):
        output = hu.execute('arp', '-an')[0]
        for line in output.split('\n'):
            if self.gw_ip in line and not 'incomplete' in line:
                return line.split(' ')[3]
        if retry:
            hu.execute('ping', '-c3', self.gw_ip, check_exit_code=False)
            return self._get_default_route_mac(False)
        return None

    def get_default_route_mac(self):
        return self._get_default_route_mac(True)

    def get_namespace(self, iface_id):
        return 'vm-%s' % iface_id

    @lockutils.synchronized('hypernode-plug-unplug')
    def plug(self, instance_id, hyper_vif, provider_vif):
        LOG.debug("hyper_vif=%s" % hyper_vif)
        LOG.debug("provider_vif=%s" % provider_vif)
        provider_ip = provider_vif.get('ip')
        #provider_mac = provider_vif.get('mac')
        br_trans_veth, p_ns_veth = self.get_veth_pair_names3(
            hyper_vif.get('id'))

        h_ns_veth = self.create_br_vnic(instance_id, hyper_vif)

        # - create a namespace: vm-id
        vm_ns = vm_namespace.VMNameSpace(
            self.get_namespace(hyper_vif.get('id')))
        vm_ns.create()

        # remove the veth pair
        hu.delete_net_dev(br_trans_veth)
        hu.delete_net_dev(p_ns_veth)

        hu.create_veth_pair(br_trans_veth, p_ns_veth)

        hu.ovs_vsctl(['--', '--if-exists', 'del-port', br_trans_veth,
                      '--', 'add-port',
                      self.br_trans, br_trans_veth])

        # add the flows
        eth_port = self.get_port_id(self.nic)
        tvo_port = self.get_port_id(br_trans_veth)
        
        # phys_IP
        h_mac = hyper_vif['address'].strip()
        gw_mac = self.get_default_route_mac()
        x_provider_ip = provider_ip.split('.')
        x_provider_ip = '{:02X}{:02X}{:02X}{:02X}'.format(*map(int, x_provider_ip))
        nic_mac = hu.get_mac(self.nic)
        for subnet in hyper_vif['network']['subnets']:
            LOG.debug("subnet: %s" % subnet)
            h_gw = subnet['gateway']['address']
            h_cidr = subnet['cidr']
            if subnet['version'] == 4:
                h_ip = subnet['ips'][0]['address']
                
                # - Add the 2 NICS and 
                vm_ns.add_nics(p_ns_veth, nic_mac, provider_ip,
                               h_ns_veth, h_mac, h_cidr, h_ip)

                # - default gateway
                vm_ns.add_default_gw(h_gw)

                # - add rule SRC_IP<->NIC
                # for provider ip access
                self.add_flow(
                    "priority=100,cookie=%(tvo_port)s,"
                    "in_port=%(eth_port)s,dl_type=0x800,"
                    "nw_src=%(provider_ip)s,actions=mod_dl_src:%(nic_mac)s,"
                    "mod_dl_dst:%(nic_mac)s,output:%(tvo_port)s" % {
                        'eth_port': eth_port,
                        'provider_ip': provider_ip,
                        'tvo_port': tvo_port,
                        'nic_mac': nic_mac})
                # for hyper ip direct access
                self.add_flow(
                    "priority=100,cookie=%(tvo_port)s,"
                    "in_port=%(eth_port)s,dl_type=0x800,"
                    "nw_src=%(h_ip)s,actions=mod_nw_src:%(provider_ip)s,"
                    "mod_dl_src:%(nic_mac)s,"
                    "mod_dl_dst:%(nic_mac)s,output:%(tvo_port)s" % {
                        'eth_port': eth_port,
                        'h_ip': h_ip,
                        'provider_ip': provider_ip,
                        'tvo_port': tvo_port,
                        'nic_mac': nic_mac})
                self.add_flow(
                    "priority=100,cookie=%(tvo_port)s,"
                    "in_port=%(tvo_port)s,dl_type=0x800,"
                    "actions=output:%(eth_port)s" % {
                        'eth_port': eth_port,
                        'tvo_port': tvo_port})
                self.add_flow(
                    "priority=200,cookie=%(tvo_port)s,in_port=%(eth_port)s,"
                    "dl_type=0x800,nw_src=%(provider_ip)s,nw_dst=%(h_ip)s,"
                    "actions=mod_nw_src:%(h_ip)s,mod_nw_dst:%(provider_ip)s,"
                    "mod_dl_src:%(nic_mac)s,mod_dl_dst:%(gw_mac)s,"
                    "in_port" % {
                        'tvo_port': tvo_port,
                        'eth_port': eth_port,
                        'provider_ip': provider_ip,
                        'h_ip': h_ip,
                        'nic_mac': nic_mac,
                        'gw_mac': gw_mac})

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
                   'cookie=%(tvo_port)s/-1' % { 'tvo_port': tvo_port},
                   check_exit_code=False,
                   run_as_root=True)
