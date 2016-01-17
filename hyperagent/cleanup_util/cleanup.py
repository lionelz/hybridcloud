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
