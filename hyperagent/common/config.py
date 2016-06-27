from oslo_config import cfg

from oslo_log import log as logging

import oslo_messaging as messaging

from nova.i18n import _

from hyperagent import version


messaging.set_transport_defaults(control_exchange='hyperagent')

LOG = logging.getLogger(__name__)

# import the configuration options
cfg.CONF.import_opt('host', 'nova.netconf')
cfg.CONF.import_opt('rootwrap_config', 'nova.utils')
cfg.CONF.set_default('rootwrap_config', '/etc/hyperagent/rootwrap.conf')
cfg.CONF.import_opt('ovs_vsctl_timeout', 'nova.network.linux_net')
cfg.CONF.import_opt('network_device_mtu', 'nova.network.linux_net')

AGENT_OPTS = [
    cfg.StrOpt('root_helper', default='sudo',
               help=_('Root helper application.')),
    cfg.FloatOpt('report_interval', default=30,
                 help=_('Seconds between nodes reporting state to server; '
                        'should be less than agent_down_time, best if it '
                        'is half or less than agent_down_time.')),
]

cfg.CONF.register_opts(AGENT_OPTS, 'AGENT')

hyper_agent_default_opts = [
    cfg.StrOpt('hyper_agent_vif_driver',
               default='hyperagent.agent.vif_agent.AgentVMVIFDriver',
               help='The Hyper Agent VIF Driver'),
    cfg.IntOpt('network_device_mtu_overhead',
               default='50',
               help='The encapsulation overhead length (default 50=vxlan)'),
]

cfg.CONF.register_opts(hyper_agent_default_opts)


def init(args, **kwargs):
    product_name = "hyperagent"
    logging.register_options(cfg.CONF)
    logging.setup(cfg.CONF, product_name)
    cfg.CONF(args=args, project=product_name,
             version='%%(prog)s %s' % version.version_info.release_string(),
             **kwargs)
    from nova import rpc as n_rpc
    n_rpc.init(cfg.CONF)


def get_root_helper(conf):
    return conf.AGENT.root_helper
