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
from oslo.vmware import api
from oslo.vmware import vim

from nova.compute import power_state
from nova.compute import task_states
from nova import image
from nova.openstack.common import log as logging
from nova.openstack.common import fileutils as fileutils
from nova.virt import driver
from nova.virt.hybrid.common import fake_driver
from nova.virt.hybrid.common import common_tools
from nova.virt.hybrid.vcloud import hyper_agent_api
from nova.virt.hybrid.vcloud import util
from nova.virt.hybrid.vcloud import vcloud_task_states
from nova.virt.hybrid.vcloud.vcloud import VCLOUD_STATUS
from nova.virt.hybrid.vcloud.vcloud_client import VCloudClient
from nova.volume.cinder import API as cinder_api

vcloudapi_opts = [

    cfg.StrOpt('vcloud_node_name',
               default='vcloud_node_01',
               help='node name, which a node is a vcloud vcd'
               'host.'),
    cfg.StrOpt('vcloud_host_ip',
               help='Hostname or IP address for connection to VMware VCD '
               'host.'),
    cfg.IntOpt('vcloud_host_port',
               default=443,
               help='Host port for cnnection to VMware VCD '
               'host.'),
    cfg.StrOpt('vcloud_host_username',
               help='Host username for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('vcloud_host_password',
               help='Host password for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('vcloud_org',
               help='User org for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('vcloud_vdc',
               help='Vdc for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('vcloud_version',
               default='5.5',
               help='Version for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('vcloud_service',
               default='85-719',
               help='Service for connection to VMware VCD '
               'host.'),
    cfg.BoolOpt('vcloud_verify',
                default=False,
                help='Verify for connection to VMware VCD '
                'host.'),
    cfg.StrOpt('vcloud_service_type',
               default='vcd',
               help='Service type for connection to VMware VCD '
               'host.'),
    cfg.IntOpt('vcloud_api_retry_count',
               default=2,
               help='Api retry count for connection to VMware VCD '
               'host.'),
    cfg.StrOpt('vcloud_conversion_dir',
               default='/vcloud/convert_tmp',
               help='the directory where images are converted in '),
    cfg.StrOpt('vcloud_volumes_dir',
               default='/vcloud/volumes',
               help='the directory of volume files'),
    cfg.StrOpt('vcloud_vm_naming_rule',
               default='openstack_vm_id',
               help='the rule to name vcloud VMs, valid options:'
               'openstack_vm_id, openstack_vm_name, cascaded_openstack_rule'),
    cfg.DictOpt('vcloud_flavor_map',
                default={
                    'm1.tiny': '1',
                    'm1.small': '2',
                    'm1.medium': '3',
                    'm1.large': '4',
                    'm1.xlarge': '5'},
                help='map nova flavor name to vcloud vm specification id'),
    cfg.StrOpt('metadata_iso_catalog',
               default='metadata-isos',
               help='The metadata iso cotalog.'),
    cfg.StrOpt('provider_api_network_name',
               help='The provider network name which api provider network use.'),
    cfg.StrOpt('provider_tunnel_network_name',
               help='The provider network name which tunnel provider network use.'),
]

status_dict_vapp_to_instance = {
    VCLOUD_STATUS.FAILED_CREATION: power_state.CRASHED,
    VCLOUD_STATUS.UNRESOLVED: power_state.BUILDING,
    VCLOUD_STATUS.RESOLVED: power_state.BUILDING,
    VCLOUD_STATUS.DEPLOYED: power_state.NOSTATE,
    VCLOUD_STATUS.SUSPENDED: power_state.SUSPENDED,
    VCLOUD_STATUS.POWERED_ON: power_state.RUNNING,
    VCLOUD_STATUS.WAITING_FOR_INPUT: power_state.NOSTATE,
    VCLOUD_STATUS.UNKNOWN: power_state.NOSTATE,
    VCLOUD_STATUS.UNRECOGNIZED: power_state.NOSTATE,
    VCLOUD_STATUS.POWERED_OFF: power_state.SHUTDOWN,
    VCLOUD_STATUS.INCONSISTENT_STATE: power_state.NOSTATE,
    VCLOUD_STATUS.MIXED: power_state.NOSTATE,
    VCLOUD_STATUS.DESCRIPTOR_PENDING: power_state.NOSTATE,
    VCLOUD_STATUS.COPYING_CONTENTS: power_state.NOSTATE,
    VCLOUD_STATUS.DISK_CONTENTS_PENDING: power_state.NOSTATE,
    VCLOUD_STATUS.QUARANTINED: power_state.NOSTATE,
    VCLOUD_STATUS.QUARANTINE_EXPIRED: power_state.NOSTATE,
    VCLOUD_STATUS.REJECTED: power_state.NOSTATE,
    VCLOUD_STATUS.TRANSFER_TIMEOUT: power_state.NOSTATE,
    VCLOUD_STATUS.VAPP_UNDEPLOYED: power_state.NOSTATE,
    VCLOUD_STATUS.VAPP_PARTIALLY_DEPLOYED: power_state.NOSTATE,
}


CONF = cfg.CONF
CONF.register_opts(vcloudapi_opts, 'vcloud')


LOG = logging.getLogger(__name__)


IMAGE_API = image.API()


class VCloudDriver(fake_driver.FakeNovaDriver):
    """The VCloud host connection object."""

    def __init__(self, virtapi, scheme="https"):
        self._node_name = CONF.vcloud.vcloud_node_name
        self._vcloud_client = VCloudClient(scheme=scheme)
        self.cinder_api = cinder_api()

        if not os.path.exists(CONF.vcloud.vcloud_conversion_dir):
            os.makedirs(CONF.vcloud.vcloud_conversion_dir)

        if not os.path.exists(CONF.vcloud.vcloud_volumes_dir):
            os.makedirs(CONF.vcloud.vcloud_volumes_dir)

        self.hyper_agent_api = hyper_agent_api.HyperAgentAPI()
        super(VCloudDriver, self).__init__(virtapi)

    def _update_vm_task_state(self, instance, task_state):
        instance.task_state = task_state
        instance.save()

    def spawn(self, context, instance, image_meta, injected_files,
              admin_password, network_info=None, block_device_info=None):
        LOG.info('begin time of vcloud create vm is %s' %
                  (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))

        image_cache_dir = CONF.vcloud.vcloud_conversion_dir
        volume_cache_dir = CONF.vcloud.vcloud_volumes_dir

        this_conversion_dir = '%s/%s' % (CONF.vcloud.vcloud_conversion_dir, 
                                         instance.uuid)
        fileutils.ensure_tree(this_conversion_dir)
        os.chdir(this_conversion_dir)
        #0: create metadata iso and upload to vcloud
        iso_file = common_tools.create_user_data_iso(
            "userdata.iso",
            {"rabbit_userid": CONF.rabbit_userid,
             "rabbit_password": CONF.rabbit_password,
             "rabbit_host": CONF.rabbit_hosts[0],
             "host": instance.uuid},
            this_conversion_dir)
        vapp_name = self._get_vcloud_vapp_name(instance)
        metadata_iso = self._vcloud_client.upload_metadata_iso(iso_file,
                                                               vapp_name)

        # 0.get vorg, user name,password vdc  from configuration file (only one
        # org)

        # 1.1 get image id, vm info ,flavor info
        # image_uuid = instance.image_ref
        if 'id' in image_meta:
            # create from image
            image_uuid = image_meta['id']
        else:
            # create from volume
            image_uuid = image_meta['properties']['image_id']

        vm_flavor_name = instance.get_flavor().name
        vcloud_flavor_id = CONF.vcloud.vcloud_flavor_map[vm_flavor_name]
        vm_task_state = instance.task_state

        # 2~3 get vmdk file. check if the image or volume vmdk file cached first
        converted_file_name = this_conversion_dir + \
            '/converted-file.vmdk'

        block_device_mapping = driver.block_device_info_get_mapping(
            block_device_info)

        image_vmdk_file_name = '%s/%s.vmdk' % (
            image_cache_dir, image_uuid)

        volume_file_name = ''
        if len(block_device_mapping) > 0:
            volume_id = block_device_mapping[0][
                'connection_info']['data']['volume_id']
            volume_file_name = '%s/%s.vmdk' % (
                volume_cache_dir, volume_id)

        # 2.1 check if the image or volume vmdk file cached
        if os.path.exists(volume_file_name):
            # if volume cached, move the volume file to conversion dir
            shutil.move(volume_file_name, converted_file_name)
        elif os.path.exists(image_vmdk_file_name):
            LOG.debug("the image file exist,copy image file %s to converted_file %s " \
                       %(image_vmdk_file_name,converted_file_name))
            # if image cached, copy ghe image file to conversion dir
            shutil.copy2(image_vmdk_file_name, converted_file_name)
            LOG.debug("end copy image file %s to converted_file %s " \
                       %(image_vmdk_file_name,converted_file_name))
            
        else:
            LOG.debug("begin download image file %s " %(image_uuid))
            # if NOT cached, download qcow2 file from glance to local, then convert it to vmdk
            # tmp_dir = '/hctemp'
            self._update_vm_task_state(
                instance,
                task_state=vcloud_task_states.DOWNLOADING)

            metadata = IMAGE_API.get(context, image_uuid)
            file_size = int(metadata['size'])
            read_iter = IMAGE_API.download(context, image_uuid)
            glance_file_handle = util.GlanceFileRead(read_iter)

            orig_file_name = this_conversion_dir + \
                '/' + image_uuid + '.tmp'
            orig_file_handle = fileutils.file_open(orig_file_name, "wb")

            util.start_transfer(context,
                                glance_file_handle,
                                file_size,
                                write_file_handle=orig_file_handle,
                                task_state=vcloud_task_states.DOWNLOADING,
                                instance=instance)

            # 2.2. convert to vmdk
            self._update_vm_task_state(
                instance,
                task_state=vcloud_task_states.CONVERTING)

            common_tools.convert_vm(metadata["disk_format"],
                                    orig_file_name,
                                    'vmdk',
                                    converted_file_name)

            LOG.debug("copy image file %s to converted_file %s " \
                       %(image_vmdk_file_name,converted_file_name))
            shutil.copy2(converted_file_name,image_vmdk_file_name)

        # 3. vmdk to ovf
        self._update_vm_task_state(
            instance,
            task_state=vcloud_task_states.PACKING)

        vmx_file_dir = '%s/%s' % (CONF.vcloud.vcloud_conversion_dir,'vmx')
        vmx_name = 'base-%s.vmx' % vcloud_flavor_id
        vmx_cache_full_name = '%s/%s' % (vmx_file_dir, vmx_name)
        vmx_full_name = '%s/%s' % (this_conversion_dir, vmx_name)
        
        LOG.debug("copy vmx_cache file %s to vmx_full_name %s " \
                       %(vmx_cache_full_name,vmx_full_name))
        shutil.copy2(vmx_cache_full_name, vmx_full_name)
        
        LOG.debug("end copy vmx_cache file %s to vmx_full_name %s " \
                       %(vmx_cache_full_name,vmx_full_name))

        ovf_name = '%s/%s.ovf' % (this_conversion_dir, instance.uuid)

        mk_ovf_cmd = 'ovftool -o %s %s' % \
                     (vmx_full_name, ovf_name)

        LOG.debug("begin run command %s " %(mk_ovf_cmd))
        mk_ovf_result = subprocess.call(mk_ovf_cmd, shell=True) 
        LOG.debug("end run command %s " %(mk_ovf_cmd))

        if mk_ovf_result != 0:
            LOG.error('make ovf failed!')
            self._update_vm_task_state(instance, task_state=vm_task_state)
            return

        # upload ovf to vcloud
        self._update_vm_task_state(
            instance,
            task_state=vcloud_task_states.IMPORTING)
        self._vcloud_client.upload_vm(
            ovf_name,
            vapp_name,
            CONF.vcloud.provider_tunnel_network_name,
            CONF.vcloud.provider_api_network_name)

        self._update_vm_task_state(
            instance,
            task_state=vcloud_task_states.VM_CREATING)
        expected_vapp_status = VCLOUD_STATUS.POWERED_OFF

        vapp_status = self._vcloud_client.get_vcloud_vapp_status(vapp_name)
        LOG.debug('vapp status: %s' % vapp_status)
        retry_times = 60
        while vapp_status != expected_vapp_status and retry_times > 0:
            time.sleep(3)
            vapp_status = self._vcloud_client.get_vcloud_vapp_status(vapp_name)
            LOG.debug('vapp status: %s' % vapp_status)
            retry_times = retry_times - 1

        # modified cpu
        if(instance.get_flavor().vcpus != 1):
            if self._vcloud_client.modify_vm_cpu(vapp_name,
                                                 instance.get_flavor().vcpus):
                LOG.info("modified %s cpu success" % vapp_name)

        # mount it
        self._vcloud_client.insert_media(vapp_name, metadata_iso)

        # power on it
        self._vcloud_client.power_on_vapp(vapp_name)

        # 7. clean up
        self._update_vm_task_state(instance, task_state=vm_task_state)
        shutil.rmtree(this_conversion_dir, ignore_errors=True)
        LOG.info('end time of vcloud create vm is %s' %
                  (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))

    def _get_vcloud_vapp_name(self, instance):
        if CONF.vcloud.vcloud_vm_naming_rule == 'openstack_vm_id':
            return instance.uuid
        elif CONF.vcloud.vcloud_vm_naming_rule == 'openstack_vm_name':
            return instance.display_name
        elif CONF.vcloud.vcloud_vm_naming_rule == 'cascaded_openstack_rule':
            return instance.display_name
        else:
            return instance.uuid

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

    #TODO: test it
    def snapshot(self, context, instance, image_id, update_task_state):

        update_task_state(task_state=task_states.IMAGE_PENDING_UPLOAD)
        # 1. get vmdk url
        vapp_name = self._get_vcloud_vapp_name(instance)
        remote_vmdk_url = self._vcloud_client.query_vmdk_url(vapp_name)

        # 2. download vmdk
        temp_dir = '%s/%s' % (CONF.vcloud.vcloud_conversion_dir, instance.uuid)
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

    def reboot(self, context, instance, network_info, reboot_type,
               block_device_info=None, bad_volumes_callback=None):
        LOG.debug('[vcloud nova driver] begin reboot instance: %s' %
                  instance.uuid)
        vapp_name = self._get_vcloud_vapp_name(instance)

        try:
            self._vcloud_client.reboot_vapp(vapp_name)
        except Exception as e:
            LOG.error('reboot instance %s failed, %s' % (vapp_name, e))

    def power_off(self, instance, shutdown_timeout=0, shutdown_attempts=0):
        LOG.debug('[vcloud nova driver] begin reboot instance: %s' %
                  instance.uuid)
        vapp_name = self._get_vcloud_vapp_name(instance)
        try:
            self._vcloud_client.power_off_vapp(vapp_name)
        except Exception as e:
            LOG.error('power off failed, %s' % e)

    def power_on(self, context, instance, network_info, block_device_info):
        vapp_name = self._get_vcloud_vapp_name(instance)
        self._vcloud_client.power_on_vapp(vapp_name)

    def _do_destroy_vm(self, context, instance, network_info, block_device_info=None,
                       destroy_disks=True, migrate_data=None):

        vapp_name = self._get_vcloud_vapp_name(instance)
        try:
            self._vcloud_client.power_off_vapp(vapp_name)
        except Exception as e:
            LOG.error('power off failed, %s' % e)

        vm_task_state = instance.task_state
        self._update_vm_task_state(instance, vm_task_state)
        try:
            self._vcloud_client.delete_vapp(vapp_name)
        except Exception as e:
            LOG.error('delete vapp failed %s' % e)
        try:
            self._vcloud_client.delete_metadata_iso(vapp_name)
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

    def get_info(self, instance):
        state = power_state.NOSTATE
        try:
            vapp_name = self._get_vcloud_vapp_name(instance)
            vapp_status = self._vcloud_client.get_vcloud_vapp_status(vapp_name)
            state = status_dict_vapp_to_instance.get(vapp_status)
        except Exception as e:
            LOG.info('can not find the vapp %s' % e)

        return {'state': state,
                'max_mem': 0,
                'mem': 0,
                'num_cpu': 1,
                'cpu_time': 0}

    def get_available_nodes(self, refresh=False):
        return [self._node_name]

    def plug_vifs(self, instance, network_info):
        LOG.debug("plug_vifs")
        # TODO: retrieve provider info ips/macs for vcloud
        for vif in network_info:
            self.hyper_agent_api.plug(instance.uuid, vif, None)

    def unplug_vifs(self, instance, network_info):
        LOG.debug("unplug_vifs")
        for vif in network_info:
            self.hyper_agent_api.unplug(instance.uuid, vif)
