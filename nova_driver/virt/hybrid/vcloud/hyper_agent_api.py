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

from oslo import messaging
from oslo.config import cfg

from nova import context as nova_context
from nova import objects
from nova import rpc
from nova.compute import utils as compute_utils
from nova.objects import base as objects_base
from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)

hyper_agent_api_opts = [  
    cfg.IntOpt('plug_retry_timeout',
               default=15,
               help='timeout for each connect retry for a new VM'),
    cfg.IntOpt('plug_retries_max',
               default=8,
               help='Maximal number of connect retries before giving up'),
]


cfg.CONF.register_opts(hyper_agent_api_opts, 'hyper_agent_api')


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
        LOG.debug("get_vifs_for_instance %s" % instance_id)
        instance = objects.Instance.get_by_uuid(
            nova_context.get_admin_context(), instance_id)
        net_info = compute_utils.get_nw_info_for_instance(instance)
        # TODO: retrieve the provider_net_info (IP/MAC)
        return {'net_info': net_info,
                'provider_net_info': [None, None, None]}

    def get_vifs_for_hyper_node(self, context, **kwargs):
        """Return the list of VIF for an hyper node."""
        hyper_node_id = kwargs['hyper_node_id']
        # TODO: implementation that return all the instances of the CN


class HyperAgentAPI(object):
    """Client side of the Hyper Node RPC API
    """
    plug_retries_max = cfg.CONF.hyper_agent_api.plug_retries_max
    plug_retry_timeout = cfg.CONF.hyper_agent_api.plug_retry_timeout

    def __init__(self):
        target = messaging.Target(topic='hyper-agent-vif-update',
                                  version='1.0',
                                  exchange='hyperagent')
        serializer = objects_base.NovaObjectSerializer()
        self.client = rpc.get_client(target, serializer=serializer)
        self.client.timeout = HyperAgentAPI.plug_retry_timeout
        self.context = nova_context.get_admin_context()
        self.call_back = HyperAgentCallback()
        super(HyperAgentAPI, self).__init__()

    def choose_hn(self):
        pass

    def plug(self, instance_id, hyper_vif, provider_vif):
        """
        waits for the Hyper Agent to be ready and connects the instance
        """
        count = 1
        LOG.debug('HyperAgentAPI:plug - plug %s, %s, %s' %
                  (str(instance_id), str(hyper_vif), str(provider_vif)))
        while True:
            try:
                self.client.cast(self.context, 'plug',
                                 instance_id=instance_id,
                                 hyper_vif=hyper_vif,
                                 provider_vif=provider_vif)
                LOG.debug('HyperAgentAPI:plug - plug returned')
                return True
            except Exception as e:
                LOG.debug('HyperAgentAPI:plug - encountered an exception: %s' %
                          e)
                count += 1
                if count > HyperAgentAPI.plug_retries_max:
                    LOG.debug('HyperAgentAPI:plug - Max retries exceeded,'
                              'raising exception')
                    raise e
        
    def unplug(self, instance_id, hyper_vif):
        """
        Disconnects an instance
        """
        try:
            return self.client.cast(self.context,
                                    'unplug',
                                    instance_id=instance_id,
                                    hyper_vif=hyper_vif)
        except Exception as e:
            LOG.error('Unplug return error:%s' % (str(e),))
            return None