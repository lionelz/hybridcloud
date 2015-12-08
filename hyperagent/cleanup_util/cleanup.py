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


from oslo.config import cfg

from nova.openstack.common import importutils

from hyperagent.common import config
from hyperagent.agent import hyper_agent


def main():
    config.register_root_helper(cfg.CONF)
    config.register_agent_state_opts_helper(cfg.CONF)
    cfg.CONF.register_opts(hyper_agent.hyper_agent_default_opts)
    config.init(sys.argv[1:])
    config.setup_logging()
    vif_driver = importutils.import_object(cfg.CONF.hyper_agent_vif_driver)
    vif_driver.cleanup()


if __name__ == "__main__":
    main()
