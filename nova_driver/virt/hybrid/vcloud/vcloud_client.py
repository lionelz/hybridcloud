import re
import requests
import subprocess
import time

from lxml import etree
from nova import exception
from nova.compute import power_state
from nova_driver.virt.hybrid.common import provider_client
from nova_driver.virt.hybrid.vcloud import vcloud
from oslo_config import cfg
from oslo_log import log as logging
from pyvcloud import Http
from StringIO import StringIO
from pyvcloud.schema.vcd.v1_5.schemas.vcloud import vcloudType,vAppType,\
    taskType

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
TAG_PATTERN = re.compile(r'({.*})?(.*)')


class VCLOUD_STATUS:
    """
     status Attribute Values for VAppTemplate, VApp, Vm, and Media Objects
    """

    FAILED_CREATION = -1
    UNRESOLVED = 0
    RESOLVED = 1
    DEPLOYED = 2
    SUSPENDED = 3
    POWERED_ON = 4
    WAITING_FOR_INPUT = 5
    UNKNOWN = 6
    UNRECOGNIZED = 7
    POWERED_OFF = 8
    INCONSISTENT_STATE = 9
    MIXED = 10
    DESCRIPTOR_PENDING = 11
    COPYING_CONTENTS = 12
    DISK_CONTENTS_PENDING = 13
    QUARANTINED = 14
    QUARANTINE_EXPIRED = 15
    REJECTED = 16
    TRANSFER_TIMEOUT = 17
    VAPP_UNDEPLOYED = 18
    VAPP_PARTIALLY_DEPLOYED = 19


STATUS_DICT_VAPP_TO_INSTANCE = {
    VCLOUD_STATUS.FAILED_CREATION: power_state.CRASHED,
    VCLOUD_STATUS.UNRESOLVED: power_state.NOSTATE,
    VCLOUD_STATUS.RESOLVED: power_state.NOSTATE,
    VCLOUD_STATUS.DEPLOYED: power_state.NOSTATE,
    VCLOUD_STATUS.SUSPENDED: power_state.SUSPENDED,
    VCLOUD_STATUS.POWERED_ON: power_state.RUNNING,
    VCLOUD_STATUS.WAITING_FOR_INPUT: power_state.NOSTATE,
    VCLOUD_STATUS.UNKNOWN: power_state.NOSTATE,
    VCLOUD_STATUS.UNRECOGNIZED: power_state.NOSTATE,
    VCLOUD_STATUS.POWERED_OFF: power_state.SHUTDOWN,
    VCLOUD_STATUS.INCONSISTENT_STATE: power_state.NOSTATE,
    VCLOUD_STATUS.MIXED: power_state.NOSTATE,
    VCLOUD_STATUS.DESCRIPTOR_PENDING: power_state.NOSTATE,
    VCLOUD_STATUS.COPYING_CONTENTS: power_state.NOSTATE,
    VCLOUD_STATUS.DISK_CONTENTS_PENDING: power_state.NOSTATE,
    VCLOUD_STATUS.QUARANTINED: power_state.NOSTATE,
    VCLOUD_STATUS.QUARANTINE_EXPIRED: power_state.NOSTATE,
    VCLOUD_STATUS.REJECTED: power_state.NOSTATE,
    VCLOUD_STATUS.TRANSFER_TIMEOUT: power_state.NOSTATE,
    VCLOUD_STATUS.VAPP_UNDEPLOYED: power_state.NOSTATE,
    VCLOUD_STATUS.VAPP_PARTIALLY_DEPLOYED: power_state.NOSTATE,
}


class VCloudClient(provider_client.ProviderClient):

    def __init__(self, scheme):
        self._catalog_name = CONF.vcloud.catalog_name
        self._session = vcloud.VCloudAPISession(
            host_ip=CONF.vcloud.host_ip,
            host_port=CONF.vcloud.host_port,
            server_username=CONF.vcloud.host_username,
            server_password=CONF.vcloud.host_password,
            org=CONF.vcloud.org,
            vdc=CONF.vcloud.vdc,
            version=CONF.vcloud.version,
            verify=CONF.vcloud.verify,
            service_type=CONF.vcloud.service_type,
            retry_count=CONF.hybrid_driver.api_retry_count,
            create_session=True,
            scheme=scheme)

    @property
    def org(self):
        return self._session.org

    @property
    def username(self):
        return self._session.username

    @property
    def password(self):
        return self._session.password

    @property
    def vdc(self):
        return self._session.vdc

    @property
    def host_ip(self):
        return self._session.host_ip

    def _get_vcloud_vdc(self):
        return self._invoke_api("get_vdc",
                                self._session.vdc)

    def _get_vcloud_vapp(self, vapp_name):
        the_vapp = self._invoke_api("get_vapp",
                                    self._get_vcloud_vdc(),
                                    vapp_name)

        if not the_vapp:
            LOG.info("can't find the vapp %s" % vapp_name)
            return None
        else:
            return the_vapp

    def _invoke_vapp_task_api(self, vapp_name, method_name, *args, **kwargs):
        the_vapp = self._get_vcloud_vapp(vapp_name)
        task = self._invoke_obj_api(the_vapp, method_name, *args, **kwargs)
        if not task:
            a = ''
            for arg in args:
                a = '%s, %s' % (a, arg)
            raise exception.NovaException(
                "Unable to call %s.%s(%s)" % (str(the_vapp), method_name , a))
        self._invoke_api("block_until_completed", task)

    def _invoke_api(self, method_name, *args, **kwargs):
        res = self._session.invoke_api(self._session.vca,
                                       method_name,
                                       *args, **kwargs)
        LOG.info("_invoke_api (%s, %s, %s) = %s" %
                 (method_name, args, kwargs, res))
        return res

    def _invoke_obj_api(self, obj, method_name, *args, **kwargs):
        res = self._session.invoke_api(obj, method_name, *args, **kwargs)
        LOG.info("_invoke_obj_api (%s, %s, %s) = %s" %
                 (method_name, args, kwargs, res))
        return res

    def get_vm_status(self, instance, name):
        return STATUS_DICT_VAPP_TO_INSTANCE[
            self._get_vcloud_vapp(name).me.status]

    def power_off(self, instance, name):
        the_vapp = self._get_vcloud_vapp(name)

        vapp_status = self._get_status_first_vm(name)
        expected_vapp_status = VCLOUD_STATUS.POWERED_OFF
        if vapp_status == expected_vapp_status:
            return the_vapp

        self._invoke_vapp_task_api(name, "undeploy")

        self.wait_for_status(instance, name, expected_vapp_status)

        return the_vapp

    def _get_first_vm(self, vapp_name):
        the_vapp = self._get_vcloud_vapp(vapp_name)
        children = the_vapp.me.get_Children()
        if children:
            vms = children.get_Vm()
            for vm in vms:
                return vm

    def _get_first_vm_name(self, vapp_name):
        return self._get_first_vm(vapp_name).get_name()

    def _get_status_first_vm(self, vapp_name):
        return self._get_first_vm(vapp_name).get_status()

    def wait_for_status(self, instance, name, expected_vapp_status):
        vapp_status = self._get_vcloud_vapp(name).me.status
        LOG.debug('vapp status: %s' % vapp_status)
        retry_times = 100
        while vapp_status != expected_vapp_status and retry_times > 0:
            time.sleep(10)
            vapp_status = self._get_vcloud_vapp(name).me.status
            # add error status check and throw exception
            if vapp_status == VCLOUD_STATUS.FAILED_CREATION:
                raise exception.NovaException(
                    "VApp %s on status Error" % (name))
            LOG.debug('vapp status: %s, expected: %s, it remains %s tries' % (
                vapp_status, expected_vapp_status, retry_times))
            retry_times = retry_times - 1

    def power_on(self, instance, name):
        the_vapp = self._get_vcloud_vapp(name)

        vapp_status = self._get_status_first_vm(name)
        expected_vapp_status = VCLOUD_STATUS.POWERED_ON
        if vapp_status == expected_vapp_status:
            return the_vapp

        self._invoke_vapp_task_api(name, "poweron")

        self.wait_for_status(instance, name, expected_vapp_status)

        return the_vapp

    def delete(self, instance, name):
        self._invoke_vapp_task_api(name, "delete")

    def reboot(self, instance, name):
        self._invoke_vapp_task_api(name, "reboot")

    def insert_media(self, vapp_name, media_name):
        self.wait_media_for_status(media_name, VCLOUD_STATUS.RESOLVED)

        media = self._invoke_api("get_media",
                                 self._catalog_name,
                                 media_name)
        vm_name = self._get_first_vm_name(vapp_name)
        self._invoke_vapp_task_api(vapp_name,
                                   'vm_media',
                                   vm_name,
                                   media,
                                   'insert')

    def upload_temptale(self, ovf_name, template_name):
        cmd = ('ovftool --acceptAllEulas --vCloudTemplate="true" %s '
               '"vcloud://%s:%s@%s?org=%s&vdc=%s&vappTemplate=%s&catalog=%s"' %
               (ovf_name,
                self.username,
                self.password,
                self.host_ip,
                self.org,
                self.vdc,
                template_name,
                self._catalog_name))
        LOG.debug("begin run create template command '%s'." % cmd)
        cmd_result = subprocess.call(cmd, shell=True)
        LOG.debug("end run create template command '%s: %s'." % (
            cmd, cmd_result))
        if cmd_result != 0:
            raise exception.NovaException(
                "Unable to upload vm %s" % template_name)

    def _get(self, href):
        response = Http.get(
            href,
            headers=self._session.vca.vcloud_session.get_vcloud_headers(),
            verify=CONF.vcloud.verify)
        if response.status_code == requests.codes.ok:
            return response
        return None

    def _put(self, href, body):
        response = Http.put(
            href,
            data=body,
            headers=self._session.vca.vcloud_session.get_vcloud_headers(),
            verify=CONF.vcloud.verify)
        if response.status_code == requests.codes.accepted:
            return taskType.parseString(response.content, True)
        return None

    def _post(self, href, body, content_type):
        headers = self._session.vca.vcloud_session.get_vcloud_headers()
        headers['Content-type'] = content_type
        response = Http.post(
            href,
            data=body,
            headers=headers,
            verify=CONF.vcloud.verify)
        print response.content
        if response.status_code == requests.codes.accepted:
            return taskType.parseString(response.content, True)
        return None

    def get_media_entity(self, name):
        media = self._invoke_api("get_media", self._catalog_name, name)
        response = self._get(media.get('href'))
        if response:
            return etree.parse(StringIO(response.content))
        return None

    def get_media_status(self, name):
        media = self.get_media_entity(name)
        if media:
            for name, value in media.getroot().attrib.items():
                if name == 'status':
                    return int(value)
        return None

    def wait_media_for_status(self, name, expected_status):
        media_status = self.get_media_status(name)
        LOG.debug('media %s status: %s' % (name, media_status))
        retry_times = 100
        while media_status != expected_status and retry_times > 0:
            time.sleep(10)
            media_status = self.get_media_status(name)
            # add error status check and throw exception
            if media_status == VCLOUD_STATUS.FAILED_CREATION:
                raise exception.NovaException(
                    "Media %s on status Error" % (name))
            LOG.debug('media status: %s, expected: %s, '
                      'it remains %s tries' % (
                            media_status,
                            expected_status,
                            retry_times))
            retry_times = retry_times - 1

    def get_item(self, item_name):
        catalogs = self._invoke_api("get_catalogs")
        for catalog in catalogs:
            if self._catalog_name != catalog.name:
                continue
            if catalog.CatalogItems and catalog.CatalogItems.CatalogItem:
                for catalog_item in catalog.CatalogItems.CatalogItem:
                    if item_name == catalog_item.name:
                        return catalog_item

    def create_vapp_from_template(self,
                                  vapp_name,
                                  template_name,
                                  mem_size,
                                  cpus,
                                  net_list):
        # wait for status catalog item ready
        self.wait_media_for_status(template_name, VCLOUD_STATUS.POWERED_OFF)
        # no cpu/vm_name network change is supported during instance creation
        # API version 5.5 
        task = self._invoke_api("create_vapp",
                                self._session.vdc,
                                vapp_name,
                                template_name,
                                self._catalog_name)
        if not task:
            raise exception.NovaException(
                "Unable to create instance %s from template %s" % (
                        vapp_name, template_name))
        self._invoke_api("block_until_completed", task)

        # change cpu and memory
        self._customize_vm( vapp_name, mem_size, cpus)

        task = self._connect_vapp_to_networks(vapp_name, net_list)
        if not task:
            raise exception.NovaException(
                "Unable to connect vapp to networks (%s)" % vapp_name)
        self._invoke_api("block_until_completed", task)

        # change the vm configuration
        task = self._connect_vm(vapp_name, net_list)
        if not task:
            raise exception.NovaException(
                "Unable to connect vm to networks (%s)" % vapp_name)
        self._invoke_api("block_until_completed", task)

    def get_net_conf(self, instance, net_list, name):
        nets_conf = list()
        vm = self._get_first_vm(name)
        sections = vm.get_Section()
        networkConnectionSection = filter(lambda section:
            section.__class__.__name__ == "NetworkConnectionSectionType",
            sections)[0]
        for nc in networkConnectionSection.get_NetworkConnection():
            index = int(nc.get_NetworkConnectionIndex())
            net_conf = {
                'name': nc.get_network(),
                'device': 'eth%d' % index,
                'index': index,
                'mac': nc.get_MACAddress(),
            }
            mode = nc.get_IpAddressAllocationMode().lower()
            if mode == 'dhcp':
                net_conf['mode'] = 'dhcp'
            else: 
                net_conf['mode'] = 'static'
                net_conf['ip'] = nc.get_IpAddress()
            net = net_list[index]
            if 'neutron_id' in net:
                net_conf['neutron_id'] = net['neutron_id']
            nets_conf.append(net_conf)
        the_vapp = self._get_vcloud_vapp(name)
        vApp_NetworkConfigSection = [
            section for section in the_vapp.me.get_Section()
            if section.__class__.__name__ == "NetworkConfigSectionType"][0]
        for nc in vApp_NetworkConfigSection.get_NetworkConfig():
            ip_scope = nc.get_Configuration().get_IpScopes().get_IpScope()[0]
            for net_conf in nets_conf:
                if net_conf['name'] == nc.get_networkName():
                    net_conf['gateway'] = ip_scope.get_Gateway()
                    net_conf['netmask'] = ip_scope.get_Netmask()
                    ri = nc.get_Configuration().get_RouterInfo()
                    if ri:
                        net_conf['external_ip'] = ri.get_ExternalIp()
        return nets_conf

    def _connect_vm(self, vapp_name, net_list):
        vm = self._get_first_vm(vapp_name)
        href = vm.get_href()
        
        # vm name
        vm.set_name(vapp_name)

        sections = vm.get_Section()
        vm.set_Section([])

        # network configuration
        index = 0
        networkConnectionSection = filter(lambda section:
            section.__class__.__name__ == "NetworkConnectionSectionType",
            sections)[0]
        for net in net_list:
            networkConnection = vcloudType.NetworkConnectionType()
            networkConnection.set_network(net['id'])
            networkConnection.set_NetworkConnectionIndex(index)
            if net['mode'].startswith('dhcp'):
                networkConnection.set_IpAddressAllocationMode('DHCP')
            else:
                networkConnection.set_IpAddressAllocationMode('POOL')
            if 'mac' in net:
                networkConnection.set_MACAddress(net['mac'])
            networkConnection.set_IsConnected(True)
            networkConnectionSection.add_NetworkConnection(networkConnection)
            index += 1
        vm.add_Section(networkConnectionSection)
        output = StringIO()
        vm.export(output,
            0,
            name_ = 'Vm',
            namespacedef_ = 'xmlns="http://www.vmware.com/vcloud/v1.5" ' +
            'xmlns:vmw="http://www.vmware.com/vcloud/v1.5" ' +
            'xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" ' +
            'xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/' +
            'cim-schema/2/CIM_ResourceAllocationSettingData"',
            pretty_print = True)
        body = output.getvalue().replace("vmw:Info", "ovf:Info").replace(
            "class:", "rasd:").replace(
                "vmw:ResourceType", "rasd:ResourceType").replace(
                    'ovf:NetworkConnectionSection',
                    'vmw:NetworkConnectionSection')
        return self._post(href + '/action/reconfigureVm',
                          body,
                          'application/vnd.vmware.vcloud.vm+xml')

    def _connect_vapp_to_networks(self, vapp_name, net_list):
        the_vapp = self._get_vcloud_vapp(vapp_name)
        vApp_NetworkConfigSection = [
            section
            for section in the_vapp.me.get_Section()
            if section.__class__.__name__ == "NetworkConfigSectionType"][0]
        link = [
            link
            for link in vApp_NetworkConfigSection.get_Link()
            if link.get_type() ==
                "application/vnd.vmware.vcloud.networkConfigSection+xml"][0]

        networkConfigSection = vcloudType.NetworkConfigSectionType()
        networkConfigSection.set_Info(
            vAppType.cimString(valueOf_="Network config"))
        # add the new configuration
        n = 2 # the natRouted index
        for net in net_list:
            network_href = self._invoke_api("get_admin_network_href",
                                            self._session.vdc,
                                            net['name'])

            configuration = vcloudType.NetworkConfigurationType()
            parentNetwork = vcloudType.ReferenceType(href=network_href,
                                                     name=net['id'])
            configuration.set_ParentNetwork(parentNetwork)
            if net['mode'] == 'dhcp_static':
                configuration.set_FenceMode('natRouted')
                ipScopes = vcloudType.IpScopesType()
                ipScope = vcloudType.IpScopeType()
                ipScope.set_Gateway('192.168.%d.1' % n)
                ipScope.set_Netmask('255.255.255.248')

                ipRanges = vcloudType.IpRangesType()
                ipRange = vcloudType.IpRangeType()
                ipRange.set_StartAddress('192.168.%d.5' % n)
                ipRange.set_EndAddress('192.168.%d.6' % n)
                ipRanges.add_IpRange(ipRange)

                ipScope.set_IpRanges(ipRanges)
                ipScope.set_IsInherited(False)
                ipScope.set_IsEnabled(True)
                ipScopes.add_IpScope(ipScope)
                configuration.set_IpScopes(ipScopes)

                configuration.set_RetainNetInfoAcrossDeployments(True)

                dhcp = vcloudType.DhcpServiceType()
                dhcp.original_tagname_ = 'DhcpService'
                dhcp.set_IsEnabled(True)
                dhcp.set_DefaultLeaseTime(3600)
                dhcp.set_MaxLeaseTime(7200)
                ipRange = vcloudType.IpRangeType()
                ipRange.set_StartAddress('192.168.%d.2' % n)
                ipRange.set_EndAddress('192.168.%d.4' % n)
                dhcp.set_IpRange(ipRange)

                firewall = vcloudType.FirewallServiceType()
                firewall.original_tagname_ = 'FirewallService'
                firewall.set_IsEnabled(True)
                firewall.set_DefaultAction('drop')
                firewall.set_LogDefaultAction(False)
                firewall_rule = vcloudType.FirewallRuleType()
                firewall_rule.set_IsEnabled(True)
                firewall_rule.set_MatchOnTranslate(False)
                firewall_rule.set_Description('Allow all outgoing traffic')
                firewall_rule.set_Policy('allow')
                protocols = vcloudType.ProtocolsType()
                protocols.set_Any(True)
                firewall_rule.set_Protocols(protocols)
                firewall_rule.set_Port(-1)
                firewall_rule.set_DestinationPortRange('any')
                firewall_rule.set_DestinationIp('external')
                firewall_rule.set_SourcePort(-1)
                firewall_rule.set_SourcePortRange('any')
                firewall_rule.set_SourceIp('internal')
                firewall_rule.set_EnableLogging(False)
                firewall.add_FirewallRule(firewall_rule)

                nat = vcloudType.NatServiceType()
                nat.original_tagname_ = 'NatService'
                nat.set_IsEnabled(True)
                nat.set_NatType('portForwarding')
                nat.set_Policy('allowTraffic')

                features = vcloudType.GatewayFeaturesType()
                features.add_NetworkService(dhcp)
                features.add_NetworkService(firewall)
                features.add_NetworkService(nat)
                configuration.set_Features(features)
                n += 1
            else:
                configuration.set_FenceMode('bridged')

            networkConfig = vcloudType.VAppNetworkConfigurationType()
            networkConfig.set_networkName(net['id'])
            networkConfig.set_Configuration(configuration)
            info = vcloudType.Msg_Type()
            info.set_valueOf_("Configuration parameters for logical networks")
            networkConfigSection.add_NetworkConfig(networkConfig)

        output = StringIO()
        networkConfigSection.export(
            output,
            0,
            name_ = 'NetworkConfigSection',
            namespacedef_ =
                'xmlns="http://www.vmware.com/vcloud/v1.5" ' +
                'xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1"',
            pretty_print = True)
        body = output.getvalue().replace('Info msgid=""', "ovf:Info").replace(
            "Info", "ovf:Info").replace(":vmw", "").replace(
                "vmw:","").replace("RetainNetovf", "ovf").replace(
                    "ovf:InfoAcrossDeployments","RetainNetInfoAcrossDeployments")
        return self._put(link.get_href(), body)


    def _customize_vm(self, vapp_name, mem_size, cpus):
        # change the vm configuration

        LOG.debug('mem_size, cpus=%s, %s' % (mem_size, cpus))
        vm_name = self._get_first_vm_name(vapp_name)
        self._invoke_vapp_task_api(vapp_name,
                                   'modify_vm_memory',
                                   vm_name,
                                   int(mem_size))
        self._invoke_vapp_task_api(vapp_name,
                                  'modify_vm_cpu',
                                   vm_name,
                                   int(cpus))

    def _upload_metadata_iso(self, iso_file, media_name, overwrite=False):
        overw = ''
        if overwrite:
            overw = '--overwrite'
        cmd = ('ovftool %s --sourceType="ISO" '
               ' --vCloudTemplate="false"'
               ' "%s" "vcloud://%s:%s@%s?org=%s&vdc=%s&media=%s'
               '&catalog=%s"' %
               (overw,
                iso_file,
                self.username,
                self.password,
                self.host_ip,
                self.org,
                self.vdc,
                media_name,
                self._catalog_name))
        LOG.debug("begin run upload iso command '%s'." % cmd)
        cmd_result = subprocess.call(cmd, shell=True)
        LOG.debug("end run upload iso command '%s'." % cmd)
        return cmd_result

    def upload_metadata_iso(self, iso_file, vapp_name):
        media_name = "metadata_%s.iso" % vapp_name
        try:
            cmd_result = self._upload_metadata_iso(iso_file, media_name)
        except Exception as e:
            cmd_result = 1
            LOG.error('upload meta-data failed without overwrite %s.' % (e))
        if cmd_result != 0:
            cmd_result = self._upload_metadata_iso(iso_file, media_name, True)
        if cmd_result != 0:
            raise exception.NovaException(
                "Unable to upload meta-data iso file %s" % vapp_name)
        return media_name

    def delete_metadata_iso(self, vapp_name):
        media_name = "metadata_%s.iso" % vapp_name
        return self._invoke_api("delete_catalog_item",
                                self._catalog_name,
                                media_name)
# class Mock(object):
#     def __init__(self, **entries):
#         self.__dict__.update(entries)
# 
# if __name__ == "__main__":
#     vc = Mock(**{
#         'catalog_name': 'metadata-isos',
#         'host_ip': '192.168.10.73',
#         'host_port': 443,
#         'host_username': 'a-user',
#         'host_password': 'a-user',
#         'org': 'VDF-ORG',
#         'vdc': 'vdf-vdc',
#         'version': '5.5',
#         'verify': False,
#         'service_type': 'vcd'
#     })
#     hd = Mock(**{
#         'api_retry_count': 1
#     })
#     CONF = Mock(**{
#         'hybrid_driver': hd,
#         'vcloud': vc
#     })
#  
#     vapp_name = '7f068121-09fd-4394-941e-16f04388bae5'
#     client = VCloudClient('https')
#     client.get_net_conf(None, vapp_name)
#     task = client._connect_vapp_to_networks(
#         vapp_name,
#         [('net0', 'lionel-vm1', 'natRouted', 'DHCP'),
#          ('net1', 'lionel-vm1', 'natRouted', 'DHCP')])
#     if not task:
#         raise exception.NovaException("_connect_vapp_to_networks")
#     client._invoke_api("block_until_completed", task)
#     task = client._connect_vm(vapp_name,
#                               [('net0', 'lionel-vm1', 'natRouted', 'DHCP'),
#                                ('net1', 'lionel-vm1', 'natRouted', 'DHCP')])
#     if not task:
#         raise exception.NovaException("_connect_vm")
#     client._invoke_api("block_until_completed", task)
