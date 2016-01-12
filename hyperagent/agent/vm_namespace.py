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


class VMNameSpace(object):

    def __init__(self, vm_namespace):
        self.vm_namespace = vm_namespace

    def create(self):
        if hu.netns_exists(self.vm_namespace):
            hu.execute('ip', 'netns', 'del', self.vm_namespace,
                       run_as_root=True)
        hu.execute('ip', 'netns', 'add', self.vm_namespace,
                   run_as_root=True)

    def _add_nic(self, nic_name, mac_adress, cidr):
        hu.execute('ip', 'link', 'set', nic_name,
                   'netns', self.vm_namespace,
                   run_as_root=True)
        hu.execute('ip', 'netns', 'exec', self.vm_namespace,
                   'ip', 'link', 'set', nic_name, 'up',
                   run_as_root=True)
        hu.execute('ip', 'netns', 'exec', self.vm_namespace,
                   'ip', 'addr', 'add', cidr,
                   'dev', nic_name,
                   run_as_root=True)
        hu.execute('ip', 'netns', 'exec', self.vm_namespace,
                   'ip', 'link', 'set', nic_name,
                   'address', mac_adress,
                   run_as_root=True)

    def add_nics(self,
                 p_nic_name, p_mac_adress, p_ip,
                 h_nic_name, h_mac_adress, h_cidr, h_ip):
        # Provider NIC
        p_ip_tab = p_ip.split('.')
        self._add_nic(
            p_nic_name,
            p_mac_adress,
            '%s.%s.%s.1/24' % (p_ip_tab[0], p_ip_tab[1], p_ip_tab[2])
        )

        # Hyper NIC
        h_cidr_ip = h_ip + '/' + h_cidr.split('/')[1]
        self._add_nic(h_nic_name, h_mac_adress, h_cidr_ip)

        # - set IPv4 routing in this namespace
        hu.execute('ip', 'netns', 'exec', self.vm_namespace,
                   'sysctl', '-w', 'net.ipv4.ip_forward=1',
                   run_as_root=True)

        # - Add iptables SNAT/DNAT
        hu.execute('ip', 'netns', 'exec', self.vm_namespace,
                   'iptables', '-t', 'nat', '-A', 'POSTROUTING',
                   '-s', '%s/32' % p_ip,
                   '-o', h_nic_name, '-j', 'SNAT', '--to', h_ip,
                   run_as_root=True)
        hu.execute('ip', 'netns', 'exec', self.vm_namespace,
                   'iptables', '-t', 'nat', '-A', 'PREROUTING',
                   '-d', '%s/32' % h_ip,
                   '-i', h_nic_name, '-j', 'DNAT', '--to', p_ip,
                   run_as_root=True)

    def add_default_gw(self, h_gw):
        hu.execute('ip', 'netns', 'exec', self.vm_namespace,
                   'ip', 'route', 'add', 'default',
                   'via', h_gw,
                   run_as_root=True)
