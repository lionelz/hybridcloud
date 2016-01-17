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
import os

from oslo.config import cfg

from nova.openstack.common import processutils
from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


def _get_root_helper():
    if CONF.workarounds.disable_rootwrap:
        cmd = 'sudo'
    else:
        cmd = 'sudo hyper-agent-rootwrap %s' % CONF.rootwrap_config
    return cmd


def execute(*cmd, **kwargs):
    """Convenience wrapper around oslo's execute() method."""
    if 'run_as_root' in kwargs and 'root_helper' not in kwargs:
        kwargs['root_helper'] = _get_root_helper()
    return processutils.execute(*cmd, **kwargs)


def get_mac(nic):
    r = execute('cat', '/sys/class/net/%s/address' % nic)
    return r[0].strip()


def device_exists(device):
    """Check if ethernet device exists."""
    return os.path.exists('/sys/class/net/%s' % device)


def netns_exists(name):
    output = execute('ip', 'netns', 'list',
                     run_as_root=True)[0]
    for line in output.split('\n'):
        if name == line.strip():
            return True
    return False


def ovs_vsctl(args):
    full_args = ['ovs-vsctl', '--timeout=%s' % CONF.ovs_vsctl_timeout] + args
    return execute(*full_args, run_as_root=True)


def delete_net_dev(dev):
    """Delete a network device only if it exists."""
    if device_exists(dev):
        execute('ip', 'link', 'delete', dev, run_as_root=True,
                check_exit_code=False)
        LOG.debug("Net device removed: '%s'", dev)


def create_veth_pair(dev1_name, dev2_name):
    """Create a pair of veth devices with the specified names,
    deleting any previous devices with those names.
    """
    for dev in [dev1_name, dev2_name]:
        delete_net_dev(dev)

    execute('ip', 'link', 'add', dev1_name, 'type', 'veth', 'peer',
            'name', dev2_name, run_as_root=True)
    for dev in [dev1_name, dev2_name]:
        execute('ip', 'link', 'set', dev, 'up', run_as_root=True)
        execute('ip', 'link', 'set', dev, 'promisc', 'on',
                      run_as_root=True)
        set_device_mtu(dev)


def set_device_mtu(dev, mtu=None):
    """Set the device MTU."""

    if not mtu:
        mtu = CONF.network_device_mtu
    if mtu:
        execute('ip', 'link', 'set', dev, 'mtu',
                mtu, run_as_root=True,
                check_exit_code=[0, 2, 254])


def create_ovs_vif_port(bridge, dev, iface_id, mac, instance_id):
    ovs_vsctl(['--', '--if-exists', 'del-port', dev, '--',
               'add-port', bridge, dev,
               '--', 'set', 'Interface', dev,
               'external-ids:iface-id=%s' % iface_id,
               'external-ids:iface-status=active',
               'external-ids:attached-mac=%s' % mac,
               'external-ids:vm-uuid=%s' % instance_id])
    set_device_mtu(dev)


def delete_ovs_vif_port(bridge, dev):
    ovs_vsctl(['--', '--if-exists', 'del-port', bridge, dev])
    delete_net_dev(dev)


def del_bridge(br_name):
    ovs_vsctl(['--if-exists', 'del-br', br_name])
