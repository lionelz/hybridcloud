from hyperagent.common import hyper_agent_utils as hu
from hyperagent.common import hyper_vif_driver

from oslo_concurrency import lockutils

from oslo_config import cfg

from oslo_log import log as logging


LOG = logging.getLogger(__name__)
NIC_NAME_LEN = 14

hyper_host_opts = [
    cfg.BoolOpt('ip_tables',
                default=False,
                help=''),
]


cfg.CONF.register_opts(hyper_host_opts, 'hyperagent')

class AgentVMVIFDriver(hyper_vif_driver.HyperVIFDriver):
    """VIF driver for hypervm networking."""

    def __init__(self, *args, **kwargs):
        self.call_back = kwargs.get('call_back')
        self.instance_id = kwargs.get('instance_id')
        super(AgentVMVIFDriver, self).__init__()

    def startup_init(self):
        net_info = self.call_back.get_vifs_for_instance(self.instance_id)
        for vif in net_info:
            self.plug(self.instance_id, vif)

    def cleanup(self):
        # nothing to do
        pass

    def get_br_name(self, iface_id):
        return ("qbr" + iface_id)[:NIC_NAME_LEN]

    def get_veth_pair_names(self, iface_id):
        return (("qvm%s" % iface_id)[:NIC_NAME_LEN],
                ("qvo%s" % iface_id)[:NIC_NAME_LEN])

    def get_tap_name(self, iface_id):
        return ("tap%s" % iface_id)[:NIC_NAME_LEN]

    def get_veth_pair_names2(self, iface_id):
        return (self.get_tap_name(iface_id),
                ("tvo%s" % iface_id)[:NIC_NAME_LEN])

    def get_bridge_name(self, vif):
        br_int = vif['network']['bridge']
        if br_int:
            return br_int
        return 'br-int'

    def get_ovs_interfaceid(self, vif):
        return vif.get('ovs_interfaceid') or vif.get('id')

    def create_br_vnic(self, instance_id, vif):
        iface_id = self.get_ovs_interfaceid(vif)
        qbr_veth, br_int_veth = self.get_veth_pair_names(vif.get('id'))

        # veth for br-int creation
        if not hu.device_exists(qbr_veth):
            hu.create_veth_pair(br_int_veth, qbr_veth)

        # add in br-int the veth
        hu.create_ovs_vif_port(self.get_bridge_name(vif),
                               br_int_veth, iface_id,
                               vif['address'], instance_id)

        if cfg.CONF.hyperagent.ip_tables:
            br_name = self.get_br_name(vif.get('id'))

            tap_veth, vnic_veth = self.get_veth_pair_names2(vif.get('id'))
            # veth for virtual nic creation
            if not hu.device_exists(vnic_veth):
                hu.create_veth_pair(tap_veth, vnic_veth)

            hu.set_device_mtu(tap_veth, True)

            # linux bridge creation
            hu.create_linux_bridge(br_name, [qbr_veth, tap_veth])
        else:
            vnic_veth = qbr_veth

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
        hu.delete_linux_bridge(br_name)
        return t2_name

    @lockutils.synchronized('hypervm-plug-unplug')
    def plug(self, instance_id, hyper_vif):
        LOG.debug("hyper_vif=%s" % hyper_vif)
        vnic_veth = self.create_br_vnic(instance_id, hyper_vif)
        for subnet in hyper_vif['network']['subnets']:
            LOG.debug("subnet: %s" % subnet)
            if subnet['version'] == 4:
                # set the IP/mac on the vnic
                h_cidr = subnet['cidr']
                h_ip = subnet['ips'][0]['address']
                h_cidr_ip = h_ip + '/' + h_cidr.split('/')[1]
                hu.set_mac_ip(vnic_veth, hyper_vif['address'], h_cidr_ip)
                # remove default route
                hu.execute('ip', 'route', 'del', '0/0',
                           check_exit_code=False,
                           run_as_root=True)
                # set the default route if defined
                h_gw = None
                if subnet.get('gateway'):
                    h_gw = subnet['gateway'].get('address')
                    if h_gw:
                        hu.execute('ip', 'route', 'add', 'default',
                                   'via', h_gw,
                                   run_as_root=True)
        # set MTU
        hu.set_device_mtu(vnic_veth, True)

    @lockutils.synchronized('hypervm-plug-unplug')
    def unplug(self, hyper_vif):
        LOG.debug("unplug=%s" % hyper_vif)
        self.remove_br_vnic(hyper_vif)
