import shlex
import time
import os

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils, strutils
from nova.api.validation.parameter_types import mac_address

eventlet = importutils.try_import('eventlet')
if eventlet and eventlet.patcher.is_monkey_patched(time):
    from eventlet.green import subprocess
else:
    import subprocess

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


def _get_root_helper():
    if CONF.workarounds.disable_rootwrap:
        cmd = 'sudo'
    else:
        cmd = 'sudo /usr/bin/hyper-agent-rootwrap %s' % CONF.rootwrap_config
    return cmd


def execute(*cmd, **kwargs):
    """Convenience wrapper around oslo's execute() method."""
    if 'run_as_root' in kwargs and 'root_helper' not in kwargs:
        kwargs['root_helper'] = _get_root_helper()
    LOG.info(cmd)
    LOG.info(kwargs)
    return processutils.execute(*cmd, **kwargs)


def launch(*cmd, **kwargs):
    shell = kwargs.pop('shell', False)
    if 'run_as_root' in kwargs and 'root_helper' not in kwargs:
        kwargs['root_helper'] = _get_root_helper()
    root_helper = kwargs['root_helper']
    if 'run_as_root' in kwargs and 'root_helper' not in kwargs:
        if shell:
            # root helper has to be injected into the command string
            cmd = [' '.join((root_helper, cmd[0]))] + list(cmd[1:])
        else:
            # root helper has to be tokenized into argument list
            cmd = shlex.split(root_helper) + list(cmd)
    try:
        subprocess.Popen(cmd, shell=shell)
    except OSError as err:
        f = _('Got an OSError\ncommand: %(cmd)r\n'
                   'errno: %(errno)r')
        sanitized_cmd = strutils.mask_password(' '.join(cmd))
        LOG.error(f, {"cmd": sanitized_cmd, "errno": err.errno})
    finally:
        time.sleep(0)


def process_exist(words):
    s = subprocess.Popen(["ps", "ax"], stdout=subprocess.PIPE)
    for x in s.stdout:
        fi = True
        for word in words:
            if word not in x:
                fi = False
                break
        if fi:
            return x.split()[0]
    return False


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


def create_linux_bridge(br_name, devs=None):
    if not device_exists(br_name):
        execute('brctl', 'addbr', br_name,
                run_as_root=True)
        execute('brctl', 'setfd', br_name, 0,
                run_as_root=True)
        execute('brctl', 'stp', br_name, 'off',
                   run_as_root=True)
    execute('ip', 'link', 'set', br_name, 'up',
            run_as_root=True)
    if devs:
        for dev in devs:
            execute('brctl', 'addif', br_name, dev,
                    check_exit_code=False,
                    run_as_root=True)


def delete_linux_bridge(br_name):
    execute('ip', 'link', 'set', br_name, 'down',
            check_exit_code=False,
            run_as_root=True)
    execute('brctl', 'delbr', br_name,
            check_exit_code=False,
            run_as_root=True)


def set_device_mtu(dev, overhead=None):
    """Set the device MTU."""

    if overhead:
        mtu = CONF.network_device_mtu - CONF.network_device_mtu_overhead
    else:
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


def del_ovs_bridge(br_name):
    ovs_vsctl(['--if-exists', 'del-br', br_name])


def add_ovs_bridge(br_name, mac_address):
    ovs_vsctl(['--may-exist', 'add-br', br_name])
    ovs_vsctl(['set', 'bridge', br_name,
               'other-config:hwaddr=%s' % mac_address])


def add_ovs_port(bridge, dev):
    ovs_vsctl(['--', '--if-exists', 'del-port', dev, '--',
               'add-port', bridge, dev])


def get_nic_cidr(eth, restart=False):
    ip = None
    show = execute('ip', 'addr', 'show', eth, run_as_root=True)
    for l in show[0].split('\n'):
        if 'inet ' in l:
            for a in l.split(' '):
                if '/' in a:
                    ip = a
    if ip:
        return ip
    if restart:
        execute('ifdown', eth, run_as_root=True)
        execute('ifup', eth, run_as_root=True)
        return get_nic_cidr(eth)
    return None


def set_mac_ip(nic, mac, cidr):
    execute('ip', 'addr', 'flush', 'dev', nic,
            run_as_root=True)
    execute('ip', 'link', 'set', nic, 'address', mac,
            run_as_root=True)
    execute('ip', 'addr', 'add', cidr, 'dev', nic,
            check_exit_code=False,
            run_as_root=True)
