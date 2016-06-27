import time
import urlparse
import urllib

import oslo_messaging as messaging

from nova import context as nova_context
from nova import objects
from nova import rpc
from nova.compute import utils as compute_utils
from nova.network.neutronv2 import api as neutronapi
from nova.objects import base as objects_base

from oslo_config import cfg

from oslo_log import log as logging


LOG = logging.getLogger(__name__)


HYPER_AGENT_DRIVER = {
    'default': None,
    'agent': 'hyperagent.agent.vif_agent.AgentVMVIFDriver',
    'switch': 'hyperagent.agent.vif_hyperswitch.HyperSwitchVIFDriver',
    'lxd': 'hyperagent.agent.vif_lxd_host.LXDHostVIFDriver',
}


def get_nsize(netmask):
    binary_str = ''
    for octet in netmask.split('.'):
        binary_str += bin(int(octet))[2:].zfill(8)
    return str(len(binary_str.rstrip('0')))


def check_host_exist(neutron, host):
    agt_list = neutron.list_agents(host=host)
    LOG.debug("for host %s: %s" % (host, agt_list))
    nb_retry = 60
    while (nb_retry == 0 or not agt_list or 'agents' not in agt_list
           or len(agt_list['agents']) == 0):
        time.sleep(1)
        LOG.warn("host %s not yet known..." % host)
        agt_list = neutron.list_agents(host=host)
        LOG.debug("for host %s: %s" % (host, agt_list))
        nb_retry = nb_retry - 1


class HyperAgentCallback(object):
    """Processes the rpc call back."""

    RPC_API_VERSION = '1.0'

    def __init__(self):
        endpoints = [self]
        target = messaging.Target(topic='hyper-agent-callback',
                                  version='1.0',
                                  exchange='hyperagent',
                                  server=cfg.CONF.host)
        self.server = rpc.get_server(target, endpoints)
        self.server.start()
        super(HyperAgentCallback, self).__init__()

    def get_vifs_for_instance(self, context, **kwargs):
        """Return the list of VIF for an instance."""
        instance_id = kwargs['instance_id']
        LOG.debug('get_vifs_for_instance %s' % instance_id)
        instance = objects.Instance.get_by_uuid(
            nova_context.get_admin_context(), instance_id)
        hyper_net_info = compute_utils.get_nw_info_for_instance(instance)

        neutron = neutronapi.get_client(context, admin=True)
        check_host_exist(neutron, instance_id)
        tenant_ids = []
        LOG.debug('hyper_net_info: %s' % hyper_net_info)
        for vif in hyper_net_info:
            tenant_ids.append(vif['network']['meta']['tenant_id'])
            neutron.update_port(vif['id'],
                                {'port': {'binding:host_id': instance_id}})
        # get all the tenant router
        LOG.debug('tenant_ids: %s' % tenant_ids)
        for tenant_id in tenant_ids:
            routers = neutron.list_routers({'tenant_id': tenant_id})['routers']
            LOG.debug('routers: %s' % routers)
            for router in routers:
                neutron.update_router(router['id'],
                                      {'router': {'admin_state_up': 'False'}})
                neutron.update_router(router['id'],
                                      {'router': {'admin_state_up': 'True'}})

        return hyper_net_info

    def get_vif_for_provider_ip(self, context, **kwargs):
        """Return the VIF for a VM."""
        provider_ip = kwargs['provider_ip']
        LOG.debug("provider ip = % s" % provider_ip)
        # retrieve the instance id from the provider ip
        # from the nova metadata
        filters = {
            'filter': [{'name': 'tag:provider_ip', 'value': provider_ip}]
        }
        instances = objects.InstanceList.get_by_filters(
            context, filters=filters)
        # should return only one and check it
        if len(instances) == 1:
            instance = instances[0]
            vif_id = instance.metadata['ip_%s' % provider_ip]
            hyper_net_info = compute_utils.get_nw_info_for_instance(instance)
            hyper_vif = None
            for vif in hyper_net_info:
                if vif.get('id') == vif_id:
                    hyper_vif = vif
                    break
            neutron = neutronapi.get_client(context, admin=True)
            check_host_exist(neutron, instance.uuid)
            neutron.update_port(hyper_vif,
                                {'port': {'binding:host_id': instance.uuid}})
            return {'instance_id': instance.uuid, 'hyper_vif': hyper_vif}
        else:
            return None


class HyperAgentAPI(object):
    """Client side of the Hyper Node RPC API
    """

    def __init__(self):
        target = messaging.Target(topic='hyper-agent-vif-update',
                                  version='1.0',
                                  exchange='hyperagent')
        serializer = objects_base.NovaObjectSerializer()
        self.client = rpc.get_client(target, serializer=serializer)
        self.context = nova_context.get_admin_context()
        self.call_back = HyperAgentCallback()
        super(HyperAgentAPI, self).__init__()

    def plug(self, instance_id, hyper_vif):
        """
        plug a new vif to an instance
        """
        LOG.debug('HyperAgentAPI:plug - plug %s, %s' %
                  (str(instance_id), str(hyper_vif)))
        return self.client.cast(self.context, 'plug',
                                instance_id=instance_id,
                                hyper_vif=hyper_vif)

    def unplug(self, instance_id, hyper_vif):
        """
        unplug a vif from an instance
        """
        return self.client.cast(self.context,
                                'unplug',
                                instance_id=instance_id,
                                hyper_vif=hyper_vif)

    def get_net_list(self, network_info, image_meta):
        """

        :param network_info: network_info
        :param image_meta: image_meta
        :return: list(net_name, parent_name, fence_mode, ip_mode)
        """
        props = image_meta.get('properties')
        net_list = list()
        if 'agent_type' in props:
            # the agent needs the mgnt, data and perhaps vms 
            net_list.append({'id': 'net0',
                             'name': cfg.CONF.hybrid_driver.mgnt_network,
                             'mode': 'static'})
            net_list.append({'id': 'net1',
                             'name': cfg.CONF.hybrid_driver.data_network,
                             'mode': 'static'})
            if props['agent_type'] == 'switch':
                net_list.append({'id': 'net2',
                                 'name': cfg.CONF.hybrid_driver.vms_network,
                                 'mode': 'static'})
        else:
            # only the vms network for vpn-vms
            i = 0
            for vif in network_info:
                net_list.append({'neutron_id': vif['id'],
                                 'id': 'net%d' % i,
                                 'name': cfg.CONF.hybrid_driver.vms_network,
                                 'mode': 'dhcp_static',
                                 'mac': vif['address']})
        return net_list

    def get_user_metadata(self, instance, image_meta, nets_conf):
        """
        return the user data for an hyper switch VM
        """

        props = image_meta.get('properties')
        user_metadata = {}
        if 'agent_type' in props:
            # TODO: check privileges agent vm creation according
            #       to the agent type

            # add the data to connect to the neutron/nova services
            rabbit_hosts = None
            if cfg.CONF.hybrid_driver.external_rabbit_host:
                rabbit_hosts = cfg.CONF.hybrid_driver.external_rabbit_host
            else:
                for rabbit_host in cfg.CONF.oslo_messaging_rabbit.rabbit_hosts:
                    if rabbit_hosts:
                        rabbit_hosts = '%s, %s' % (rabbit_hosts, rabbit_host)
                    else:
                        rabbit_hosts = rabbit_host
            user_metadata.update({
                'rabbit_userid': cfg.CONF.oslo_messaging_rabbit.rabbit_userid,
                'rabbit_password': cfg.CONF.oslo_messaging_rabbit.rabbit_password,
                'rabbit_hosts': rabbit_hosts,
                'host': instance.uuid,
                # be careful to create the VM with the interface in a good order
                'network_mngt_interface': 'eth0',
                'network_data_interface': 'eth1',
                'network_vms_interface': 'eth2',
            })
            for net_conf in nets_conf:
                d = net_conf['device']
                if net_conf['mode'].startswith('dhcp'):
                    user_metadata[d] = 'dhcp'
                else:
                    if d == 'eth0' and 'gateway' in net_conf:
                        user_metadata['provider_gateway'] = net_conf['gateway']
                    user_metadata[d] = 'manual'
                    user_metadata[d + '_ip'] = net_conf['ip']
                    user_metadata[d + '_netmask'] = net_conf['netmask']
                    user_metadata[d + '_size'] = get_nsize(net_conf['netmask'])
            hyper_agent_vif_driver = HYPER_AGENT_DRIVER[props['agent_type']]
            user_metadata['container_image_uri'] = self._replace_in_uri(
                image_meta, 'container_image_uri')
            user_metadata['container_rootfs_uri'] = self._replace_in_uri(
                image_meta, 'container_rootfs_uri')
            user_metadata['hyper_agent_vif_driver'] = hyper_agent_vif_driver
            user_metadata['network_device_mtu'] = 1500
            user_metadata['network_device_mtu_overhead'] = 50
        else:
            return user_metadata

        LOG.debug('user_metadata=%s' % user_metadata)
        return user_metadata


    def _replace_in_uri(self, image_meta, uri_name):
        props = image_meta.get('properties')
        if uri_name in props:
            # 'glance://demo:stack@${glance_host}:${glance_port}/?'
            # '${image_uuid}'
            # '&project_name=demo'
            # '&${auth_url}'
            # '&${scheme}'
            g_api = urlparse.urlparse(cfg.CONF.glance.api_servers[0])
            prop_s = {
                'image_uuid': self._get_my_image_uuid(image_meta),
                'auth_url': cfg.CONF.keystone_authtoken.auth_uri,
                'scheme': g_api.scheme
            }
            curi = props[uri_name]
            for k, v in prop_s.iteritems():
                curi = curi.replace('${%s}' % k,
                                    '%s=%s' % (k, urllib.quote(str(v))))
            simple_s = {
                'glance_api_servers': cfg.CONF.glance.api_servers[0],
                'glance_host': g_api.hostname,
                'glance_port': g_api.port,
            }
            for k, v in simple_s.iteritems():
                curi = curi.replace('${%s}' % k, '%s' % str(v))
            return curi

    def _get_my_image_uuid(self, image_meta):
        # create from image
        return image_meta['id']
