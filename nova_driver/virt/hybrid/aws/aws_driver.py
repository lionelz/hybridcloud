import os
import time

from nova import image

from nova.compute import hv_type

from oslo_config import cfg

from oslo_log import log as logging

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
    cfg.DictOpt('security_groups',
               help='security groups for mgnt, data and vms networks'),
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

        image_meta_dict = self._get_image_meta_dict(context, image_meta)

        # list of networks
        net_list = self.hyper_agent_api.get_net_list(network_info,
                                                     image_meta_dict)

        if not self._image_exists_in_provider(image_meta_dict):
            with image_convertor.ImageConvertorToOvf(
                context,
                self.conversion_dir,
                instance.uuid,
                self._get_image_uuid(image_meta_dict),
                vmx_name,
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
                    self._get_image_uuid(image_meta_dict)
                )

        # launch the VM

        vm_flavor_name = instance.get_flavor().name
        instance_type = cfg.CONF.aws.flavor_map[vm_flavor_name]
        image_uuid = self._get_image_uuid(image_meta_dict)
        
        user_metadata = self._get_user_metadata(
            instance, net_list, image_meta_dict)
        user_metadata['network_device_mtu'] = 9001

        if 'properties' in image_meta_dict:
            props = image_meta_dict.get('properties')
            if not 'agent_type' in props:
                i = 0
                for vif in network_info:
                    user_metadata['eth%d_mac' % i] = vif['address']
                    i = + 1

        self._provider_client.create_instance(
            instance=instance,
            name=vm_name,
            image_uuid=image_uuid,
            user_metadata=user_metadata,
            instance_type=instance_type,
            net_list=net_list,
            sec_groups=cfg.CONF.aws.security_groups
        )

        nets_conf = self._provider_client.get_net_conf(
            instance, net_list, vm_name)

        self._update_md(instance, network_info, nets_conf)

        if user_metadata and len(user_metadata) > 0:
            if 'eth0_ip' in user_metadata and 'eth1_ip' in user_metadata:
                self.plug_vifs(context, instance, network_info,
                               user_metadata['eth0_ip'],
                               user_metadata['eth1_ip'])

        LOG.info('end time of aws create vm is %s' %
                 (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))

    def destroy(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True, migrate_data=None):
        super(AWSDriver, self).destroy(
            context, instance, network_info, block_device_info,
            destroy_disks, migrate_data)
        LOG.debug('[aws nova driver] destroy: %s' % instance.uuid)
        vapp_name = self._get_vm_name(instance)
        try:
            self._provider_client.delete(instance, vapp_name)
        except Exception as e:
            LOG.error('delete failed, %s' % e)

    def get_available_nodes(self, refresh=False):
        return [self._node_name]
