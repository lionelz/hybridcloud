import os
import time


from oslo_config import cfg

from oslo_log import log as logging

from nova import image

from nova_driver.virt.hybrid.common import abstract_driver
from nova_driver.virt.hybrid.common import common_tools
from nova_driver.virt.hybrid.common import hybrid_task_states
from nova_driver.virt.hybrid.common import image_convertor
from nova_driver.virt.hybrid.vcloud import vcloud_client

vcloud_driver_opts = [
    cfg.StrOpt('node_name',
               default='node_01',
               help='node name, which a node is a vcloud vcd'
               'host.'),
    cfg.StrOpt('host_ip',
               help='Hostname or IP address for connection to VMware VCD '
               'host.'),
    cfg.IntOpt('host_port',
               default=443,
               help='Host port for cnnection to VMware VCD '
               'host.'),
    cfg.StrOpt('host_username',
               help='Host username for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('host_password',
               help='Host password for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('org',
               help='User org for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('vdc',
               help='Vdc for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('version',
               default='5.5',
               help='Version for connection to VMware VCD '
               'host.'),
    cfg.DictOpt('flavor_map',
                default={
                    'm1.tiny': '1',
                    'm1.small': '2',
                    'm1.medium': '3',
                    'm1.large': '4',
                    'm1.xlarge': '5'},
                help='map nova flavor name to vcloud vm specification id'),
    cfg.BoolOpt('verify',
                default=False,
                help='Verify for connection to VMware VCD '
                'host.'),
    cfg.StrOpt('service_type',
               default='vcd',
               help='Service type for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('catalog_name',
               default='metadata-isos',
               help='The catalog name for metadada isos and vapps templates.'),
]


cfg.CONF.register_opts(vcloud_driver_opts, 'vcloud')


LOG = logging.getLogger(__name__)


IMAGE_API = image.API()


class VCloudDriver(abstract_driver.AbstractHybridNovaDriver):
    """The VCloud host connection object."""

    def __init__(self, virtapi, scheme="https"):
        self._node_name = cfg.CONF.vcloud.node_name
        self._provider_client = vcloud_client.VCloudClient(scheme=scheme)

        super(VCloudDriver, self).__init__(virtapi)

    def _template_exists_in_provider(self, image_meta):
        image_uuid = self._get_image_uuid(image_meta)
        return self._provider_client.get_item(image_uuid)

    def spawn(self,
              context,
              instance,
              image_meta,
              injected_files,
              admin_password,
              network_info=None,
              block_device_info=None):
        LOG.info('begin time of vcloud create vm is %s' %
                 (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
        vm_flavor_name = instance.get_flavor().name
        vcloud_flavor_id = cfg.CONF.vcloud.flavor_map[vm_flavor_name]

        # list of networks
        net_list = self.hyper_agent_api.get_net_list(network_info, image_meta)

        vapp_name = self._get_vm_name(instance)
        template_name = self._get_image_uuid(image_meta)

        inst_st_up = abstract_driver.InstanceStateUpdater(instance)

        vmx_name = 'base-%s.vmx' % vcloud_flavor_id
        # choose a default template if it's a specific one is not present
        if not os.path.exists('%s/vmx/%s' % (self.conversion_dir,
                                             vmx_name)):
            vmx_name = 'base-template.vmx'

        LOG.debug('image_meta=%s' % image_meta)
        with image_convertor.ImageConvertorToOvf(
            context,
            self.conversion_dir,
            instance.uuid,
            template_name, # image uuid
            vmx_name,
            inst_st_up,
            instance.task_state
        ) as img_conv:

            # create and upload template only if exists
            if not self._template_exists_in_provider(image_meta):
                # download the image
                img_conv.download_image()

                # convert to an exportable format
                ovf_name = img_conv.convert_to_ovf_format()

                # upload ovf to vcloud
                inst_st_up(task_state=hybrid_task_states.IMPORTING)

                self._provider_client.upload_temptale(
                    ovf_name,
                    template_name
                )

            inst_st_up(task_state=hybrid_task_states.VM_CREATING)

            # create the vapp from the template
            self._provider_client.create_vapp_from_template(
                vapp_name,
                template_name,
                instance.get_flavor().memory_mb,
                instance.get_flavor().vcpus,
                net_list
            )

            # create metadata iso and upload to vcloud
            conversion_dir = self._get_conversion_dir(instance)
            user_metadata = self._get_user_metadata(
                instance, net_list, image_meta)
            if user_metadata and len(user_metadata) > 0:
                iso_file = common_tools.create_user_data_iso(
                    'userdata.iso',
                    user_metadata,
                    conversion_dir
                )
                media_name = self._provider_client.upload_metadata_iso(
                    iso_file, vapp_name)

            self._provider_client.wait_for_status(
                instance,
                vapp_name,
                vcloud_client.VCLOUD_STATUS.POWERED_OFF)

            # mount it
            if user_metadata and len(user_metadata) > 0:
                self._provider_client.insert_media(vapp_name, media_name)

            # power on it before get net conf to get the external ip
            self._provider_client.power_on(instance, vapp_name)

            nets_conf = self._provider_client.get_net_conf(
                instance, net_list, vapp_name)

            self._update_md(instance, network_info, nets_conf)

        LOG.info('end time of vcloud create vm is %s' %
                 (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))

    def _do_destroy_vm(self,
                       context,
                       instance,
                       network_info,
                       block_device_info=None,
                       destroy_disks=True,
                       migrate_data=None):

        vapp_name = self._get_vm_name(instance)
        try:
            self._provider_client.power_off(instance, vapp_name)
        except Exception as e:
            LOG.error('power off failed, %s' % e)

        vm_task_state = instance.task_state
        self._update_vm_task_state(instance, vm_task_state)
        try:
            self._provider_client.delete(instance, vapp_name)
        except Exception as e:
            LOG.error('delete vapp failed %s' % e)
        try:
            self._provider_client.delete_metadata_iso(vapp_name)
        except Exception as e:
            LOG.error('delete metadata iso failed %s' % e)

    def destroy(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True, migrate_data=None):
        super(VCloudDriver, self).destroy(
            context, instance, network_info, block_device_info,
            destroy_disks, migrate_data)
        LOG.debug('[vcloud nova driver] destroy: %s' % instance.uuid)
        self._do_destroy_vm(context, instance, network_info, block_device_info,
                            destroy_disks, migrate_data)

        self.cleanup(context, instance, network_info, block_device_info,
                     destroy_disks, migrate_data)

    def cleanup(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True, migrate_data=None, destroy_vifs=True):
        if destroy_vifs:
            self.unplug_vifs(instance, network_info)

        LOG.debug("Cleanup network finished", instance=instance)

    def get_available_nodes(self, refresh=False):
        return [self._node_name]
