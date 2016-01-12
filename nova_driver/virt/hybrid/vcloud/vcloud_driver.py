# Copyright 2011 OpenStack Foundation
#
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

"""
A connection to the VMware vCloud platform.
"""
import os
import subprocess
import shutil
import time
import urllib2

from oslo.config import cfg

from nova import image
from nova.compute import task_states
from nova.openstack.common import log as logging
from nova.openstack.common import fileutils
from nova_driver.virt.hybrid.common import abstract_driver
from nova_driver.virt.hybrid.common import common_tools
from nova_driver.virt.hybrid.common import hybrid_task_states
from nova_driver.virt.hybrid.common import image_convertor
from nova_driver.virt.hybrid.common import util
from nova_driver.virt.hybrid.vcloud import vcloud
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
    cfg.StrOpt('metadata_iso_catalog',
               default='metadata-isos',
               help='The metadata iso cotalog.'),
    cfg.StrOpt('mgnt_network',
               help='The network name/id of the management provider network.'),
    cfg.StrOpt('data_network',
               help='The network name/id of the data provider network.'),
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
        for vif in network_info:
            LOG.debug('vif: %s' % vif)
        conversion_dir = self._get_conversion_dir(instance)
        vm_flavor_name = instance.get_flavor().name
        vcloud_flavor_id = cfg.CONF.vcloud.flavor_map[vm_flavor_name]
        vmx_name = 'base-%s.vmx' % vcloud_flavor_id
        # choose a default template if it's a specific one is not present
        if not os.path.exists('%s/vmx/%s' % (self.conversion_dir, vmx_name)):
            vmx_name = 'base-template.vmx'
        inst_st_up = abstract_driver.InstanceStateUpdater(instance)

        LOG.debug('image_meta=%s' % image_meta)

        with image_convertor.ImageConvertorToOvf(
            context,
            self.conversion_dir,
            instance.uuid,
            self._get_image_uuid(image_meta),
            vmx_name,
            {
                'eth0-present': True,
                'eth1-present': True,
                'dvd0-present': True,
                'dvd0': 'userdata.iso',
                'memsize': instance.get_flavor().memory_mb,
                'cpu': instance.get_flavor().vcpus
            },
            inst_st_up,
            instance.task_state
        ) as img_conv:

            # download the image
            img_conv.download_image()

            # create metadata iso and upload to vcloud: move to provider driver
            iso_file = common_tools.create_user_data_iso(
                'userdata.iso',
                self._get_user_metadata(instance, image_meta),
                conversion_dir)
            vapp_name = self._get_vm_name(instance)
            metadata_iso = self._provider_client.upload_metadata_iso(
                iso_file, vapp_name)

            # convert to an exportable format
            ovf_name = img_conv.convert_to_ovf_format()

            # upload ovf to vcloud
            inst_st_up(task_state=hybrid_task_states.IMPORTING)

            self._provider_client.upload_vm(
                ovf_name,
                vapp_name,
                cfg.CONF.vcloud.mgnt_network,
                cfg.CONF.vcloud.data_network)

            inst_st_up(task_state=hybrid_task_states.VM_CREATING)
            self._provider_client.wait_for_status(
                instance,
                vapp_name,
                vcloud.VCLOUD_STATUS.POWERED_OFF)
            # mount it
            self._provider_client.insert_media(vapp_name, metadata_iso)

            # power on it
            self._provider_client.power_on(instance, vapp_name)

        LOG.info('end time of vcloud create vm is %s' %
                 (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))

    def _download_vmdk_from_vcloud(self, context, src_url, dst_file_name):

        # local_file_handle = open(dst_file_name, "wb")
        local_file_handle = fileutils.file_open(dst_file_name, "wb")

        remote_file_handle = urllib2.urlopen(src_url)
        file_size = remote_file_handle.headers['content-length']

        util.start_transfer(context, remote_file_handle, file_size,
                            write_file_handle=local_file_handle)

    def _upload_image_to_glance(
            self, context, src_file_name, image_id, instance):

        vm_task_state = instance.task_state
        file_size = os.path.getsize(src_file_name)
        read_file_handle = fileutils.file_open(src_file_name, "rb")

        metadata = IMAGE_API.get(context, image_id)

        # The properties and other fields that we need to set for the image.
        image_metadata = {"disk_format": "qcow2",
                          "is_public": "false",
                          "name": metadata['name'],
                          "status": "active",
                          "container_format": "bare",
                          "size": file_size,
                          "properties": {"owner_id": instance['project_id']}}

        util.start_transfer(context,
                            read_file_handle,
                            file_size,
                            image_id=metadata['id'],
                            image_meta=image_metadata,
                            task_state=task_states.IMAGE_UPLOADING,
                            instance=instance)
        self._update_vm_task_state(instance, task_state=vm_task_state)

    # TODO: test it
    def snapshot(self, context, instance, image_id, update_task_state):

        update_task_state(task_state=task_states.IMAGE_PENDING_UPLOAD)
        # 1. get vmdk url
        vapp_name = self._get_vm_name(instance)
        remote_vmdk_url = self._provider_client.query_vmdk_url(vapp_name)

        # 2. download vmdk
        temp_dir = '%s/%s' % (cfg.CONF.hybrid_driver.conversion_dir,
                              instance.uuid)
        fileutils.ensure_tree(temp_dir)

        vmdk_name = remote_vmdk_url.split('/')[-1]
        local_file_name = '%s/%s' % (temp_dir, vmdk_name)

        self._download_vmdk_from_vcloud(
            context,
            remote_vmdk_url,
            local_file_name)

        # 3. convert vmdk to qcow2
        converted_file_name = temp_dir + '/converted-file.qcow2'
        convert_commond = "qemu-img convert -f %s -O %s %s %s" % \
            ('vmdk',
             'qcow2',
             local_file_name,
             converted_file_name)
        convert_result = subprocess.call([convert_commond], shell=True)

        if convert_result != 0:
            # do something, change metadata
            LOG.error('converting file failed')

        # 4. upload qcow2 to image repository\
        update_task_state(task_state=task_states.IMAGE_UPLOADING,
                          expected_state=task_states.IMAGE_PENDING_UPLOAD)

        self._upload_image_to_glance(
            context,
            converted_file_name,
            image_id,
            instance)

        # 5. delete temporary files
        shutil.rmtree(temp_dir, ignore_errors=True)

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

    def attach_interface(self, instance, image_meta, vif):
        LOG.debug("attach_interface: %s, %s" % (instance, vif))

    def detach_interface(self, instance, vif):
        LOG.debug("detach_interface: %s, %s" % (instance, vif))

    def get_available_nodes(self, refresh=False):
        return [self._node_name]

    def plug_vifs(self, instance, network_info):
        LOG.debug("plug_vifs")
        # TODO: retrieve provider info ips/macs for vcloud
        for vif in network_info:
            LOG.debug('vif: %s' % vif)
            self.hyper_agent_api.plug(instance.uuid, vif, None)

    def unplug_vifs(self, instance, network_info):
        LOG.debug("unplug_vifs")
        for vif in network_info:
            self.hyper_agent_api.unplug(instance.uuid, vif)
