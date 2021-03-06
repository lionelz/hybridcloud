import sys

import eventlet
eventlet.monkey_patch()

import oslo_messaging as messaging

from oslo_config import cfg

from oslo_log import log as logging

from oslo_utils import importutils

from hyperagent.common import config

from nova import context
from nova import rpc

from nova.i18n import _LI


LOG = logging.getLogger(__name__)


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

    def get_vif_for_provider_ip(self, provider_ip):
        """Retrieve the VIFs for a provider IP."""
        return self.client.call(self.context, 'get_vif_for_provider_ip',
                                provider_ip=provider_ip)


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
            cfg.CONF.hyper_agent_vif_driver,
            instance_id=self.instance_id,
            call_back=self.call_back)

        self.vif_driver.startup_init()

        self.server.start()

    def plug(self, context, **kwargs):
        """agent hyper_vif plug message

        :param instance_id:
        :param hyper_vif:
        """
        instance_id = kwargs.get('instance_id', [])
        LOG.debug("instance_id= %s" % instance_id)
        if instance_id != self.instance_id:
            LOG.debug('not for me %s' % self.instance_id)
            return False
        hyper_vif = kwargs.get('hyper_vif', [])
        LOG.debug("hyper_agent_vif= %s" % hyper_vif)
        return self.vif_driver.plug(instance_id, hyper_vif)

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
        return self.vif_driver.unplug(hyper_vif)
        return True

    def daemon_loop(self):
        while True:
            eventlet.sleep(600)


def main():
    config.init(sys.argv[1:])

    agent = HyperAgent()
    # Start everything.
    LOG.info(_LI("Agent initialized successfully, now running. "))
    agent.daemon_loop()


if __name__ == "__main__":
    main()
