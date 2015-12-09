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
import socket
import sys

from oslo import messaging
from oslo.config import cfg

from nova.i18n import _, _LI
from nova.openstack.common import log as logging

from hyperagent import version


messaging.set_transport_defaults(control_exchange='hyperagent')

LOG = logging.getLogger(__name__)


core_opts = [
    cfg.StrOpt('host', default=socket.gethostname(),
               help=_("Hostname to be used by the neutron server, agents and "
                      "services running on this machine. All the agents and "
                      "services running on this machine must use the same "
                      "host value.")),
    cfg.IntOpt('ovs_vsctl_timeout',
               default=120,
               help='Amount of time, in seconds, that ovs_vsctl should wait '
                    'for a response from the database. 0 is to wait forever.'),
    cfg.StrOpt('rootwrap_config',
               default="/etc/hyperagent/rootwrap.conf",
               help='Path to the rootwrap configuration file to use for '
                    'running commands as root'),
    cfg.IntOpt('network_device_mtu',
               default=9001,
               help='the default MTU for each network interface created'),
]

# Register the configuration options
cfg.CONF.register_opts(core_opts)

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


