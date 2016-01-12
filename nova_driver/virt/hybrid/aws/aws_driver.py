import os
import time

from oslo.config import cfg

from nova import image

from nova.openstack.common import log as logging

from nova_driver.virt.hybrid.aws import aws_client
from nova_driver.virt.hybrid.common import abstract_driver
from nova_driver.virt.hybrid.common import image_convertor

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
    cfg.StrOpt('mgnt_network',
               help='The network name/id of the management provider network.'),
    cfg.StrOpt('security_group_mgnt_network',
               help='security group management network id'),
    cfg.StrOpt('data_network',
               help='The network name/id of the data provider network.'),
    cfg.StrOpt('security_group_data_network',
               help='security group data network id'),
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

    def _image_exists_in_provider(self, image_meta):
        image_uuid = self._get_image_uuid(image_meta)
        return self._provider_client.is_exists_image(image_uuid)

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
        vmx_name = 'base-template.vmx'
        inst_st_up = abstract_driver.InstanceStateUpdater(instance)
        vm_name = self._get_vm_name(instance)
        if not self._image_exists_in_provider(image_meta):
            with image_convertor.ImageConvertorToOvf(
                context,
                self.conversion_dir,
                instance.uuid,
                self._get_image_uuid(image_meta),
                vmx_name,
                {
                    'eth0-present': True,
                    'eth1-present': True
                },
                inst_st_up,
                instance.task_state
            ) as img_conv:

                # download
                img_conv.download_image()

                ovf_name = img_conv.convert_to_ovf_format()

                # upload all the disks in 1 image:
                ovf_dir = os.path.dirname(ovf_name)
                file_names = []
                for x in range(1, 20):
                    file_name = '%s/%s-disk%d.vmdk' % (
                        ovf_dir, instance.uuid, x)
                    if (os.path.exists(file_name)):
                        file_names += [file_name]

                # import the file as a new AMI image
                self._provider_client.import_image(
                    vm_name,
                    file_names,
                    cfg.CONF.aws.s3_bucket_tmp,
                    instance,
                    self._get_image_uuid(image_meta)
                )

        # launch the VM with 2 networks
        vm_flavor_name = instance.get_flavor().name
        instance_type = cfg.CONF.aws.flavor_map[vm_flavor_name]
        image_uuid = self._get_image_uuid(image_meta)
        self._provider_client.create_instance(
            instance=instance,
            name=vm_name,
            image_uuid=image_uuid,
            user_metadata=self._get_user_metadata(instance, image_meta),
            instance_type=instance_type,
            mgnt_net=cfg.CONF.aws.mgnt_network,
            mgnt_sec_group=cfg.CONF.aws.security_group_mgnt_network,
            data_net=cfg.CONF.aws.data_network,
            data_sec_group=cfg.CONF.aws.security_group_data_network
        )
        LOG.info('end time of aws create vm is %s' %
                 (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))

    def destroy(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True, migrate_data=None):
        LOG.debug('[aws nova driver] destroy: %s' % instance.uuid)
        vapp_name = self._get_vm_name(instance)
        try:
            self._provider_client.delete(instance, vapp_name)
        except Exception as e:
            LOG.error('delete failed, %s' % e)

    def get_available_nodes(self, refresh=False):
        return [self._node_name]
