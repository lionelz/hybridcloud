
from boto3.session import Session
from nova.openstack.common import log as logging
from oslo.config import cfg


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class AWSClient(object):

    def __init__(self,
                 aws_access_key_id,
                 aws_secret_access_key,
                 region_name):
        self.session = Session(aws_access_key_id=aws_access_key_id,
                               aws_secret_access_key=aws_secret_access_key,
                               region_name=region_name)


    