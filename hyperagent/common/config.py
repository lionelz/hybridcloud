import os
import sys

from oslo import messaging
from oslo.config import cfg

from nova.i18n import _, _LI
from nova.openstack.common import log as logging

from hyperagent import version


messaging.set_transport_defaults(control_exchange='hyperagent')

LOG = logging.getLogger(__name__)

# import the configuration options
cfg.CONF.import_opt('host', 'nova.netconf')
cfg.CONF.import_opt('rootwrap_config', 'nova.utils')
cfg.CONF.set_default('rootwrap_config', '/etc/hyperagent/rootwrap.conf')
cfg.CONF.import_opt('ovs_vsctl_timeout', 'nova.network.linux_net')
cfg.CONF.import_opt('network_device_mtu', 'nova.network.linux_net')

ROOT_HELPER_OPTS = [
    cfg.StrOpt('root_helper', default='sudo',
               help=_('Root helper application.')),
]

workarounds_opts = [
    cfg.BoolOpt('disable_rootwrap',
                default=False,
                help='This option allows a fallback to sudo for performance '
                     'reasons.'),
    ]

AGENT_STATE_OPTS = [
    cfg.FloatOpt('report_interval', default=30,
                 help=_('Seconds between nodes reporting state to server; '
                        'should be less than agent_down_time, best if it '
                        'is half or less than agent_down_time.')),
]


def init(args, **kwargs):
    cfg.CONF(args=args, project='hyperagent',
             version='%%(prog)s %s' % version.version_info.release_string(),
             **kwargs)
    from nova import rpc as n_rpc
    n_rpc.init(cfg.CONF)


def get_log_args(conf, log_file_name, **kwargs):
    cmd_args = []
    if conf.debug:
        cmd_args.append('--debug')
    if conf.verbose:
        cmd_args.append('--verbose')
    if (conf.log_dir or conf.log_file):
        cmd_args.append('--log-file=%s' % log_file_name)
        log_dir = None
        if conf.log_dir and conf.log_file:
            log_dir = os.path.dirname(
                os.path.join(conf.log_dir, conf.log_file))
        elif conf.log_dir:
            log_dir = conf.log_dir
        elif conf.log_file:
            log_dir = os.path.dirname(conf.log_file)
        if log_dir:
            cmd_args.append('--log-dir=%s' % log_dir)
        if kwargs.get('metadata_proxy_watch_log') is False:
            cmd_args.append('--metadata_proxy_watch_log=false')
    else:
        if conf.use_syslog:
            cmd_args.append('--use-syslog')
            if conf.syslog_log_facility:
                cmd_args.append(
                    '--syslog-log-facility=%s' % conf.syslog_log_facility)
    return cmd_args


def register_root_helper(conf):
    conf.register_opts(ROOT_HELPER_OPTS, 'AGENT')
    conf.register_opts(workarounds_opts, 'workarounds')


def register_agent_state_opts_helper(conf):
    conf.register_opts(AGENT_STATE_OPTS, 'AGENT')


def get_root_helper(conf):
    return conf.AGENT.root_helper


def setup_logging():
    """Sets up the logging options for a log with supplied name."""
    product_name = "hyperagent"
    logging.setup(cfg.CONF, product_name)
    LOG.info(_LI("Logging enabled!"))
    LOG.info(_LI("%(prog)s version %(version)s"),
             {'prog': sys.argv[0],
              'version': version.version_info.release_string()})
    LOG.debug("command line: %s", " ".join(sys.argv))
