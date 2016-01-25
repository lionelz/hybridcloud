import botocore
import os
import threading
import time

from boto3.session import Session

from nova import exception

from nova.compute import power_state

from oslo_log import log as logging

from nova_driver.virt.hybrid.common import hybrid_task_states
from nova_driver.virt.hybrid.common import provider_client


LOG = logging.getLogger(__name__)


class NodeState(object):
    RUNNING = 16
    PENDING = 0
    STOPPING = 64
    STOPPED = 80
    TERMINATED = 48

AWS_POWER_STATE = {
    NodeState.RUNNING: power_state.RUNNING,
    NodeState.PENDING: power_state.NOSTATE,
    NodeState.STOPPING: power_state.SHUTDOWN,
    NodeState.STOPPED: power_state.SHUTDOWN,
    NodeState.TERMINATED: power_state.CRASHED,
}


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

    def __init__(self,
                 aws_access_key_id,
                 aws_secret_access_key,
                 region_name):
        self.session = Session(aws_access_key_id=aws_access_key_id,
                               aws_secret_access_key=aws_secret_access_key,
                               region_name=region_name)
        self._region_name = region_name
        self.ec2 = self.session.client('ec2')
        self.ec2_resource = self.session.resource('ec2')
        self.s3_resource = self.session.resource('s3')

    def _create_bucket_if_not_exist(self, s3_bucket):
        # TODO: add the permission/role to the created bucket
        exists = True
        try:
            self.s3_resource.meta.client.head_bucket(Bucket=s3_bucket)
        except botocore.exceptions.ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                exists = False
        if not exists:
            self.s3_resource.create_bucket(
                Bucket=s3_bucket,
                CreateBucketConfiguration={
                    'LocationConstraint': self._region_name})

    def import_image(self, name, file_names, s3_bucket, instance, image_uuid):
        try:
            LOG.debug(file_names)
            # check if the bucket exists
            self._create_bucket_if_not_exist(s3_bucket)
            # upload the file to the bucket:
            disk_containers = []
            for file_name in file_names:
                short_file_name = os.path.basename(file_name)
                # TODO: check the response
                self.s3_resource.meta.client.upload_file(
                    file_name,
                    s3_bucket,
                    short_file_name,
                    ExtraArgs={
                        'GrantRead': 'uri="http://acs.amazonaws.com/'
                        'groups/global/AllUsers"',
                        'ContentType': 'text/plain'
                    },
                    Callback=ProgressPercentage(file_name, instance))
                disk_containers += [{
                    'Description': 'image %s' % name,
                    'UserBucket': {
                        'S3Bucket': s3_bucket,
                        'S3Key': short_file_name
                    }
                }]

            # TODO: check the response
            res = self.ec2.import_image(
                DryRun=False,
                Description='image %s' % name,
                DiskContainers=disk_containers
            )
            import_task_id = res.get('ImportTaskId')

            d_res = self.ec2.describe_import_image_tasks(
                ImportTaskIds=[import_task_id]).get('ImportImageTasks')[0]
            while d_res.get('Progress'):
                status = '%s (%s)' % (
                    hybrid_task_states.PROVIDER_PREPARING,
                    d_res.get('StatusMessage'))
                LOG.debug("instance %s: %s" % (instance.uuid, status))
                instance.task_state = status
                instance.save()
                time.sleep(15)
                d_res = self.ec2.describe_import_image_tasks(
                    ImportTaskIds=[import_task_id]).get('ImportImageTasks')[0]

            if d_res.get('Status') != 'completed':
                raise exception.NovaException(
                    "import image %s failed: %s" % (
                        name,
                        d_res.get('StatusMessage')))

            image_id = d_res.get('ImageId')
            status = '%s (%s)' % (
                hybrid_task_states.PROVIDER_PREPARING,
                d_res.get('Status'))
            LOG.debug("instance %s, %s: %s" % (instance.uuid,
                                               image_id,
                                               status))
            instance.task_state = status
            instance.save()

            waiter = self.ec2.get_waiter('image_available')
            waiter.wait(ImageIds=[image_id])

            # TODO: check the response
            self.ec2.create_tags(Resources=[image_id],
                                 Tags=[{'Key': 'hybrid_cloud_image_id',
                                        'Value': image_uuid}])
        finally:
            self.s3_resource.delete_object(
                Bucket=s3_bucket,
                Key=file_name
            )

    def create_instance(self,
                        instance,
                        name,
                        image_uuid,
                        user_metadata,
                        instance_type,
                        mgnt_net,
                        mgnt_sec_group,
                        data_net,
                        data_sec_group):
        # find the image with the hybrid_cloud_image_id tag
        image_id = None
        images = self.ec2_resource.images.filter(Filters=[{
            'Name': 'tag:hybrid_cloud_image_id',
            'Values': [image_uuid]}])
        for img in images:
            image_id = img.id
        user_data = ''
        for k, v in user_metadata.iteritems():
            user_data = '%s\n%s=%s' % (user_data, k, v)

        # create the instance
        aws_instance = self.ec2_resource.create_instances(
            ImageId=image_id,
            MinCount=1,
            MaxCount=1,
            UserData=user_data,
            InstanceType=instance_type,
            InstanceInitiatedShutdownBehavior='stop',
            NetworkInterfaces=[
                {
                    'DeviceIndex': 0,
                    'SubnetId': mgnt_net,
                    'Groups': [mgnt_sec_group],
                },
                {
                    'DeviceIndex': 1,
                    'SubnetId': data_net,
                    'Groups': [data_sec_group],
                }
            ],
        )[0]
        instance_id = aws_instance.id

        self.ec2.create_tags(Resources=[instance_id],
                             Tags=[{'Key': 'hybrid_cloud_instance_id',
                                    'Value': instance.uuid},
                                   {'Key': 'Name',
                                    'Value': name}])

        aws_instance.wait_until_running()

    def is_exists_image(self, image_uuid):
        images = self.ec2_resource.images.filter(Filters=[{
            'Name': 'tag:hybrid_cloud_image_id',
            'Values': [image_uuid]}])
        size = sum(1 for _ in images)
        if size == 1:
            return True
        return False

    def _get_instances(self, instance):
        return self.ec2_resource.instances.filter(Filters=[{
            'Name': 'tag:hybrid_cloud_instance_id',
            'Values': [instance.uuid]}])

    def get_vm_status(self, instance, vapp_name):
        instances = self._get_instances(instance)
        for aws_instance in instances:
            LOG.debug('aws_instance: %s' % aws_instance.__dict__)
            LOG.debug('aws_instance.state: %s' % aws_instance.state)
            return AWS_POWER_STATE[aws_instance.state.get('Code')]

    def power_off(self, instance, name):
        instances = self._get_instances(instance)
        for aws_instance in instances:
            aws_instance.stop()

    def power_on(self, instance, name):
        instances = self._get_instances(instance)
        for aws_instance in instances:
            aws_instance.start()

    def delete(self, instance, name):
        instances = self._get_instances(instance)
        for aws_instance in instances:
            aws_instance.stop()
            aws_instance.wait_until_stopped()
            aws_instance.terminate()
            aws_instance.wait_until_terminated()

    def reboot(self, instance, name):
        instances = self._get_instances(instance)
        for aws_instance in instances:
            aws_instance.reboot()
