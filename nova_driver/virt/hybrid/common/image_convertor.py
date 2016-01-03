import os
import shutil
import subprocess

from nova import image
from nova.openstack.common import log as logging
from nova.openstack.common import fileutils

from nova_driver.virt.hybrid.common import common_tools
from nova_driver.virt.hybrid.common import hybrid_task_states
from nova_driver.virt.hybrid.common import util

LOG = logging.getLogger(__name__)
IMAGE_API = image.API()


class ImageConvertorToOvf(object):
    
    def __init__(self,
                 context,
                 work_dir,
                 uuid,
                 image_uuid,
                 vmx_template_name,
                 vmx_template_params,
                 callback,
                 task_state):
        self._context = context
        self._image_uuid = image_uuid
        self._work_dir = work_dir
        self._uuid = uuid
        self._conversion_dir = "%s/%s" % (work_dir, uuid)
        self._vmx_template_name = vmx_template_name
        self._vmx_template_params = vmx_template_params
        self._converted_file_name = 'converted-file'
        # vmx_template_params
        # disk0, eth0-present, eth1-present,
        # eth2-present, vmname, dvd0-present, dvd0
        self._vmx_template_params['disk0'] = self._converted_file_name
        self._vmx_template_params['vmname'] = self._uuid
        for k in ('eth0-present',
                  'eth1-present',
                  'eth2-present',
                  'dvd0-present'):
            if self._vmx_template_params.get(k):
                self._vmx_template_params[k] = 'TRUE'
            else:
                self._vmx_template_params[k] = 'FALSE'
        self._callback = callback
        self._task_state = task_state

    def __enter__(self):
        LOG.debug('__enter__')
        fileutils.ensure_tree(self._conversion_dir)
        os.chdir(self._conversion_dir)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        shutil.rmtree(self._conversion_dir, ignore_errors=True)
        self._callback(task_state=self._task_state)

    def _convert_to_vmdk(self):
        self._callback(task_state=hybrid_task_states.CONVERTING)

        converted_file_name = '%s/%s.vmdk' % (self._conversion_dir,
                                              self._converted_file_name)
        orig_file_name  = '%s/%s' % (self._work_dir, self._image_uuid)
        image_vmdk_file_name = '%s/%s.vmdk' % (self._work_dir, self._image_uuid)

        # check if the image or volume vmdk cached
        if not os.path.exists(image_vmdk_file_name):
            LOG.debug("Begin download image file %s " % self._image_uuid)

            metadata = IMAGE_API.get(self._context, self._image_uuid)

            # convert to vmdk
            common_tools.convert_vm(metadata['disk_format'],
                                    orig_file_name,
                                    'vmdk',
                                    converted_file_name)

            shutil.move(converted_file_name, image_vmdk_file_name)

        # link the image file to conversion dir
        os.link(image_vmdk_file_name, converted_file_name)

        self._callback(task_state=self._task_state)


    def _convert_vmdk_to_ovf(self):
        self._callback(task_state=hybrid_task_states.PACKING)

        vmx_file_dir = '%s/%s' % (self._work_dir, 'vmx')
        vmx_cache_full_name = '%s/%s' % (vmx_file_dir, self._vmx_template_name)
        vmx_full_name = '%s/%s' % (self._conversion_dir, self._vmx_template_name)
        
        LOG.debug("copy vmx_cache file %s to vmx_full_name %s with %s" % (
            vmx_cache_full_name, vmx_full_name, self._vmx_template_params))
        common_tools.copy_replace(vmx_cache_full_name,
                                  vmx_full_name,
                                  self._vmx_template_params)
        LOG.debug("end copy vmx_cache file %s to vmx_full_name %s with %s" % (
            vmx_cache_full_name, vmx_full_name, self._vmx_template_params))

        ovf_name = '%s/%s.ovf' % (self._conversion_dir, self._uuid)

        mk_ovf_cmd = 'ovftool -o %s %s' % (vmx_full_name, ovf_name)

        LOG.debug("begin run command %s" % mk_ovf_cmd)
        mk_ovf_result = subprocess.call(mk_ovf_cmd, shell=True) 
        LOG.debug("end run command %s" % mk_ovf_cmd)

        if mk_ovf_result != 0:
            LOG.error('make ovf failed!')

        self._callback(task_state=self._task_state)
        return ovf_name

    def download_image(self):
        dest_file_name = '%s/%s' % (self._work_dir, self._image_uuid)
        if not os.path.exists(dest_file_name):
            self._callback(task_state=hybrid_task_states.DOWNLOADING)
            orig_file_name = "%s/%s.tmp" % (self._conversion_dir,
                                            self._image_uuid)
            LOG.debug("Begin download image file %s " % self._image_uuid)
    
            metadata = IMAGE_API.get(self._context, self._image_uuid)
            file_size = int(metadata['size'])

            read_iter = IMAGE_API.download(self._context, self._image_uuid)
            glance_file_handle = util.GlanceFileRead(read_iter)
    
            orig_file_handle = fileutils.file_open(orig_file_name, "wb")
    
            util.start_transfer(self._context,
                                glance_file_handle,
                                file_size,
                                write_file_handle=orig_file_handle,
                                task_state=hybrid_task_states.DOWNLOADING,
                                callback=self._callback)
            # move to dest_file_name
            shutil.move(orig_file_name, dest_file_name)
            self._callback(task_state=self._task_state)

    def convert_to_ovf_format(self):
        self._convert_to_vmdk()
        return self._convert_vmdk_to_ovf()
