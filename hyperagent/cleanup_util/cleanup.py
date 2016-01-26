import sys

from oslo_config import cfg

from oslo_utils import importutils

from hyperagent.common import config


def main():
    config.init(sys.argv[1:])
    vif_driver = importutils.import_object(cfg.CONF.hyper_agent_vif_driver)
    vif_driver.cleanup()


if __name__ == "__main__":
    main()
