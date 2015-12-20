import abc
import os
import threading

from boto3.session import Session

from nova.openstack.common import log as logging

from nova_driver.virt.hybrid.common import hybrid_task_states
from nova_driver.virt.hybrid.common import provider_client

from oslo.config import cfg


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class ProgressPercentage(object):

    def __init__(self, filename, instance):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()
        self._instance = instance
        self._last = 0

    def __call__(self, bytes_amount):
        # To simplify we'll assume this is hooked up
        # to a single filename.
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            if percentage - self._last > 0.1:
                status = '%s (%.2f%%)' % (
                    hybrid_task_states.UPLOADING, percentage)
                LOG.debug("instance %s: %s" % (self._instance.uuid, status))
                self._instance.task_state = status
                self._instance.save()
                self._last = percentage


class AWSClient(provider_client.ProviderClient):
    __metaclass__  = abc.ABCMeta

    def __init__(self,
                 aws_access_key_id,
                 aws_secret_access_key,
                 region_name):
        self.session = Session(aws_access_key_id=aws_access_key_id,
                               aws_secret_access_key=aws_secret_access_key,
                               region_name=region_name)
        
        self.ec2 = self.session.client('ec2')
        self.s3 = self.session.resource('s3')

    def import_image(self, name, vmdk_file, s3_bucket, instance):
        # upload the file to the bucket:
        res = self.s3.meta.client.upload_file(
            vmdk_file,
            s3_bucket,
            name,
            Callback=ProgressPercentage(vmdk_file, instance))
        LOG.debug(res)

#         self.ec2.import_image(
#             DryRun=False,
#             Description='image %s' % name,
#             DiskContainers=[
#                 {
#                     'Description': 'image %s' % name,
#                     'Format': 'VMDK',
#                     'UserBucket': {
#                         'S3Bucket': s3_bucket,
#                         'S3Key': file_name
#                     },
#                 }
#             ]
#         )                              

    def power_off(self, name):
        self.ec2.instances.filter(InstanceIds=[name]).stop()
        
    def power_on(self, name):
        pass

    def delete(self, name):
        pass

    def reboot(self, name):
        pass

