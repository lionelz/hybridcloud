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
import sys

import eventlet
eventlet.monkey_patch()

from oslo import messaging
from oslo.config import cfg

from hyperagent.common import config

from nova import context
from nova import rpc
from nova.i18n import _LI
from nova.openstack.common import log as logging
from nova.openstack.common import importutils


LOG = logging.getLogger(__name__)


hyper_agent_default_opts = [
    cfg.StrOpt('hyper_agent_vif_driver',
               default='hyperagent.agent.hypervm_vif.HyperVMVIFDriver',
               help='The Hyper Agent VIF Driver'),
    ]


cfg.CONF.register_opts(hyper_agent_default_opts)


class HyperAgentCallback(object):
    """Processes the rpc call back."""

    RPC_API_VERSION = '1.0'

    def __init__(self):
        target = messaging.Target(topic='hyper-agent-callback',
                                  version='1.0',
                                  exchange='hyperagent')
        self.client = rpc.get_client(target)
        self.context = context.get_admin_context()
        super(HyperAgentCallback, self).__init__()

    def get_vifs_for_instance(self, instance_id):
        """Retrieve the VIFs for the current instance."""
        return self.client.call(self.context, 'get_vifs_for_instance',
                                instance_id=instance_id)

    def get_vifs_for_hyper_node(self, hyper_node_id):
        """Retrieve the VIFs for the current hyper node."""
        return self.client.call(self.context, 'get_vifs_for_hyper_node',
                                hyper_node_id=hyper_node_id)


class HyperAgent(object):

    def __init__(self):
        super(HyperAgent, self).__init__()
        self.instance_id = cfg.CONF.host

        # the queue client for plug/unplug calls from nova driver
        endpoints = [self]
        target = messaging.Target(topic='hyper-agent-update',
                                  version='1.0',
                                  exchange='hyperagent',
                                  server=cfg.CONF.host)
        self.server = rpc.get_server(target, endpoints)

        # the call back to nova driver init
        self.call_back = HyperAgentCallback()

        # instance according to configuration
        self.vif_driver = importutils.import_object(
            cfg.CONF.hyper_agent_vif_driver, self.instance_id, self.call_back)

        self.vif_driver.startup_init()

        self.server.start()

    def plug(self, context, **kwargs):
        """agent hyper_vif plug message

        :param instance_id:
        :param hyper_vif:
        :param provider_vif:
        """
        instance_id = kwargs.get('instance_id', [])
        LOG.debug("instance_id= %s" % instance_id)
        if instance_id != self.instance_id:
            LOG.debug("not for me %s" % self.instance_id)
            return False
        hyper_vif = kwargs.get('hyper_vif', [])
        LOG.debug("hyper_agent_vif= %s" % hyper_vif)
        provider_vif = kwargs.get('provider_vif', [])
        LOG.debug("provider_vif= %s" % provider_vif)
        self.vif_driver.plug(instance_id, hyper_vif, provider_vif)
        return True

    def unplug(self, context, **kwargs):
        """agent hyper_vif unplug message

        :param instance_id:
        :param hyper_vif:
        """
        instance_id = kwargs.get('instance_id', [])
        LOG.debug("instance_id= %s" % instance_id)
        if instance_id != self.instance_id:
            LOG.debug("not for me %s" % self.instance_id)
            return False
        hyper_vif = kwargs.get('hyper_vif', [])
        LOG.debug("hyper_agent_vif= %s" % hyper_vif)
        self.vif_driver.unplug(hyper_vif)
        return True

    def daemon_loop(self):
        while True:
            eventlet.sleep(600)


def main():
    config.register_root_helper(cfg.CONF)
    config.register_agent_state_opts_helper(cfg.CONF)
    config.init(sys.argv[1:])
    config.setup_logging()

    agent = HyperAgent()
    # Start everything.
    LOG.info(_LI("Agent initialized successfully, now running... "))
    agent.daemon_loop()


if __name__ == "__main__":
    main()
