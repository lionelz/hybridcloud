import abc
import botocore
import os
import threading
import time

from boto3.session import Session

from nova import exception
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
            if percentage - self._last > 1:
                status = '%s-1 (%.1f%%)' % (
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
        self._region_name = region_name
        self.ec2 = self.session.client('ec2')
        self.s3 = self.session.resource('s3')

    def _create_bucket_if_not_exist(self, s3_bucket):
        exists = True
        try:
            self.s3.meta.client.head_bucket(Bucket=s3_bucket)
        except botocore.exceptions.ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                exists = False
        if not exists:
            self.s3.create_bucket(
                Bucket=s3_bucket,
                CreateBucketConfiguration={
                    'LocationConstraint': self._region_name})

    def import_image(self, name, file_name, s3_bucket, instance):
        # check if the bucket exists
        self._create_bucket_if_not_exist(s3_bucket)
        # upload the file to the bucket:
        res = self.s3.meta.client.upload_file(
            file_name,
            s3_bucket,
            name,
            ExtraArgs={
               'GrantRead': 'uri="http://acs.amazonaws.com/'
               'groups/global/AllUsers"',
               'ContentType': 'text/plain'},
            Callback=ProgressPercentage(file_name, instance))
        LOG.debug(res)
        res = self.ec2.import_image(
            DryRun=False,
            Description='image %s' % name,
            DiskContainers=[
                {
                    'Description': 'image %s' % name,
                    'UserBucket': {
                        'S3Bucket': s3_bucket,
                        'S3Key': name
                    },
                }
            ]
        )
        d_res = self.ec2.describe_import_image_tasks(
            ImportTaskIds=[res.get('ImportTaskId')])
        while d_res.get('ImportImageTasks')[0].get('Progress'):
            status = '%s-2 (%.1f%%)' % (
                hybrid_task_states.UPLOADING,
                float(d_res.get('ImportImageTasks')[0].get('Progress')))
            LOG.debug("instance %s: %s" % (instance.uuid, status))
            instance.task_state = status
            instance.save()
            time.sleep(15)
            d_res = self.ec2.describe_import_image_tasks(
                ImportTaskIds=[res.get('ImportTaskId')])
        if d_res.get('ImportImageTasks')[0].get('Status') != 'completed':
            raise exception.NovaException(
                "import image %s failed: %s" % (
                    name,
                    d_res.get('ImportImageTasks')[0].get('StatusMessage')))
            

    def power_off(self, name):
        self.ec2.instances.filter(InstanceIds=[name]).stop()
        
    def power_on(self, name):
        pass

    def delete(self, name):
        pass

    def reboot(self, name):
        pass

