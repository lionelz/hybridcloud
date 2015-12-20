import shutil
import time

from oslo.config import cfg

from nova import image
from nova.compute import power_state
from nova.openstack.common import log as logging

from nova_driver.virt.hybrid.aws import aws_client
from nova_driver.virt.hybrid.common import abstract_driver

aws_driver_opts = [
    cfg.StrOpt('access_key_id',
               help='the access key id for connection to aws'),
    cfg.StrOpt('secret_access_key',
               help='the secret key  for connection to EC2'),
    cfg.StrOpt('region_name',
               default='us-east-1',
               help='the region for connection to EC2'),
    cfg.StrOpt('s3_bucket_tmp',
               help='s3 bucket used for temporary space'),
    cfg.DictOpt('flavor_map',
                default={'m1.tiny': 't2.micro',
                         'm1.small': 't2.micro',
                         'm1.medium': 't2.micro',
                         'm1.large': 't2.micro',
                         'm1.xlarge': 't2.micro'},
                help='nova flavor name to aws ec2 instance type mapping'),

]


cfg.CONF.register_opts(aws_driver_opts, 'aws')


LOG = logging.getLogger(__name__)


IMAGE_API = image.API()


class AWSDriver(abstract_driver.AbstractHybridNovaDriver):
    """The AWS Hybrid NOVA driver."""

    def __init__(self, virtapi, scheme="https"):
        self._node_name = cfg.CONF.aws.region_name
        self._provider_client = aws_client.AWSClient(
            aws_access_key_id=cfg.CONF.aws.access_key_id,
            aws_secret_access_key=cfg.CONF.aws.secret_access_key,
            region_name=cfg.CONF.aws.region_name)
        super(AWSDriver, self).__init__(virtapi)

    def spawn(self,
              context,
              instance,
              image_meta,
              injected_files,
              admin_password,
              network_info=None,
              block_device_info=None):
        LOG.info('begin time of aws create vm is %s' %
                  (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))

        conversion_dir = super(AWSDriver, self).spawn(
            context,
            instance,
            image_meta,
            injected_files,
            admin_password,
            network_info,
            block_device_info
        )
        
        # import the vmdk as a new image
        vm_name = self._get_vm_name(instance)
        self._provider_client.import_image(
            vm_name,
            "%s/converted-file.vmdk" % conversion_dir,
            cfg.CONF.aws.s3_bucket_tmp,
            instance
        )
        
        # launch the VM with 2 networks

        shutil.rmtree(conversion_dir, ignore_errors=True)
        LOG.info('end time of aws create vm is %s' %
                  (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))

    def get_info(self, instance):
        state = power_state.NOSTATE
        try:
            vm_name = self._get_vm_name(instance)
#             vapp_status = self._vcloud_client.get_vcloud_vapp_status(vapp_name)
#             state = status_dict_vapp_to_instance.get(vapp_status)
        except Exception as e:
            LOG.info('can not find the VM %s' % e)

        return {'state': state,
                'max_mem': 0,
                'mem': 0,
                'num_cpu': 1,
                'cpu_time': 0}

    def get_available_nodes(self, refresh=False):
        return [self._node_name]
