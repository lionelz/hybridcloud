"""
An abstract hybrid Nova Driver implementing the common methods
"""
import os

from nova import image

from nova.compute import arch
from nova.compute import hv_type
from nova.compute import vm_mode
from nova.compute import power_state

from nova.network.neutronv2 import api as neutronapi

from oslo_log import log as logging

from nova.virt import driver
from nova.virt import hardware

from nova.volume.cinder import API as cinder_api

from nova_driver.virt.hybrid.common import hyper_agent_api

from oslo_config import cfg


LOG = logging.getLogger(__name__)


IMAGE_API = image.API()


hybrid_driver_opts = [
    cfg.StrOpt('provider',
               help='provider type (vcloud|aws)'),
    cfg.IntOpt('api_retry_count',
               default=2,
               help='Api retry count for connection to the provider.'),
    cfg.StrOpt('conversion_dir',
               default='/tmp',
               help='the directory where images are converted in'),
    cfg.StrOpt('volumes_dir',
               default='/tmp',
               help='the directory of volume files'),
    cfg.StrOpt('vm_naming_rule',
               default='openstack_vm_id',
               help='the rule to name VMs in the provider, valid options:'
               'openstack_vm_id, openstack_vm_name, cascaded_openstack_rule'),
    cfg.StrOpt('mgnt_network',
               help='The network name/id of the management provider network.'),
    cfg.StrOpt('data_network',
               help='The network name/id of the data provider network.'),
    cfg.StrOpt('vms_network',
               help='The network name/id of the VM provider network.'),
    cfg.StrOpt('external_rabbit_host',
               help='rabbit host IP to set-up n the VM (if different).'),
]


cfg.CONF.register_opts(hybrid_driver_opts, 'hybrid_driver')
cfg.CONF.import_opt('auth_uri',
                    'keystonemiddleware.auth_token',
                    'keystone_authtoken')


class InstanceStateUpdater(object):

    def __init__(self, instance):
        self._instance = instance

    def __call__(self, task_state):
        self._instance.task_state = task_state
        self._instance.save()


class AbstractHybridNovaDriver(driver.ComputeDriver):
    """The VCloud host connection object."""

    def __init__(self, virtapi):
        super(AbstractHybridNovaDriver, self).__init__(virtapi)
        self.instances = {}
        self.cinder_api = cinder_api()
        self.conversion_dir = cfg.CONF.hybrid_driver.conversion_dir
        if not os.path.exists(self.conversion_dir):
            os.makedirs(self.conversion_dir)

        self.volumes_dir = cfg.CONF.hybrid_driver.volumes_dir
        if not os.path.exists(self.volumes_dir):
            os.makedirs(self.volumes_dir)

        self.hyper_agent_api = hyper_agent_api.HyperAgentAPI()

    def _get_image_meta_dict(self, context, image_meta):
        return IMAGE_API.get(context, image_meta.id)

    def init_host(self, host):
        LOG.debug("init_host")

    def list_instances(self):
        LOG.debug("list_instances")
        return self.instances.keys()

    def _get_image_uuid(self, image_meta):
        if 'properties' in image_meta:
            props = image_meta.get('properties')
            if 'parent_image_uuid' in props:
                return props['parent_image_uuid']
            if 'parent_image_type' in props:
                # TODO: search an image with the image_type in glance
                # and return its image uuid
                pass
        return self._get_my_image_uuid(image_meta)

    def _get_my_image_uuid(self, image_meta):
        if 'id' in image_meta:
            # create from image
            return image_meta['id']
        else:
            # create from volume
            return image_meta['properties']['image_id']

    def _get_user_metadata(self, instance, net_list, image_meta):
        nets_conf = self._provider_client.get_net_conf(
            instance,
            net_list,
            self._get_vm_name(instance))
        return self.hyper_agent_api.get_user_metadata(
            instance, image_meta, nets_conf)

    def _get_conversion_dir(self, instance):
        return '%s/%s' % (self.conversion_dir, instance.uuid)

    def _image_exists_in_provider(self, image_meta):
        return False

    def _update_vm_task_state(self, instance, task_state):
        instance.task_state = task_state
        instance.save()

    def spawn(self,
              context,
              instance,
              image_meta,
              injected_files,
              admin_password,
              network_info=None,
              block_device_info=None):
        LOG.debug("spawn")

    def snapshot(self, context, instance, image_id, update_task_state):
        LOG.debug("snapshot")

    def reboot(self, context, instance, network_info, reboot_type,
               block_device_info=None, bad_volumes_callback=None):
        LOG.debug('begin reboot instance: %s' % instance.uuid)
        name = self._get_vm_name(instance)
        try:
            self._provider_client.reboot(name)
        except Exception as e:
            LOG.error('reboot instance %s failed, %s' % (name, e))

    def set_admin_password(self, instance, new_pass):
        LOG.debug("set_admin_password")

    def inject_file(self, instance, b64_path, b64_contents):
        LOG.debug("inject_file")

    def resume_state_on_host_boot(self, context, instance, network_info,
                                  block_device_info=None):
        LOG.debug("resume_state_on_host_boot")

    def rescue(self, context, instance, network_info, image_meta,
               rescue_password):
        LOG.debug("rescue")

    def unrescue(self, instance, network_info):
        LOG.debug("unrescue")

    def poll_rebooting_instances(self, timeout, instances):
        LOG.debug("poll_rebooting_instances")

    def migrate_disk_and_power_off(self, context, instance, dest,
                                   flavor, network_info,
                                   block_device_info=None,
                                   timeout=0, retry_interval=0):
        LOG.debug("migrate_disk_and_power_off")

    def finish_revert_migration(self, context, instance, network_info,
                                block_device_info=None, power_on=True):
        LOG.debug("finish_revert_migration")

    def post_live_migration_at_destination(self, context, instance,
                                           network_info,
                                           block_migration=False,
                                           block_device_info=None):
        LOG.debug("post_live_migration_at_destination")

    def power_off(self, instance, shutdown_timeout=0, shutdown_attempts=0):
        LOG.debug('begin reboot instance: %s' % instance.uuid)
        name = self._get_vm_name(instance)
        try:
            self._provider_client.power_off(instance, name)
        except Exception as e:
            LOG.error('power off failed, %s' % e)

    def power_on(self, context, instance, network_info, block_device_info):
        name = self._get_vm_name(instance)
        self._provider_client.power_on(instance, name)

    def soft_delete(self, instance):
        LOG.debug("soft_delete")

    def restore(self, instance):
        LOG.debug("restore")

    def pause(self, instance):
        LOG.debug("pause")

    def unpause(self, instance):
        LOG.debug("unpause")

    def suspend(self, instance):
        LOG.debug("suspend")

    def resume(self, context, instance, network_info, block_device_info=None):
        LOG.debug("resume")

    def destroy(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True, migrate_data=None):
        LOG.debug("destroy")
        neutron = neutronapi.get_client(context, admin=True)
        agt_list = neutron.list_agents(host=instance.uuid)
        LOG.debug("for host %s: %s" % (instance.uuid, agt_list))
        for agent in agt_list['agents']:
            neutron.delete_agent(agent=agent['id'])

    def cleanup(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True, migrate_data=None, destroy_vifs=True):
        LOG.debug("cleanup")

    def attach_volume(self, context, connection_info, instance, mountpoint,
                      disk_bus=None, device_type=None, encryption=None):
        LOG.debug("attach_volume")

    def detach_volume(self, connection_info, instance, mountpoint,
                      encryption=None):
        LOG.debug("detach_volume")

    def swap_volume(self, old_connection_info, new_connection_info,
                    instance, mountpoint, resize_to):
        LOG.debug("swap_volume")

    def get_diagnostics(self, instance_name):
        LOG.debug("get_diagnostics")

    def get_instance_diagnostics(self, instance_name):
        LOG.debug("get_instance_diagnostics")

    def get_all_bw_counters(self, instances):
        LOG.debug("get_all_bw_counters")
        return []

    def get_all_volume_usage(self, context, compute_host_bdms):
        LOG.debug("get_all_volume_usage")
        return []

    def get_host_cpu_stats(self):
        LOG.debug("get_host_cpu_stats")

    def block_stats(self, instance_name, disk_id):
        LOG.debug("block_stats")

    def interface_stats(self, instance_name, iface_id):
        LOG.debug("interface_stats")

    def get_console_output(self, context, instance):
        LOG.debug("get_console_output")
        return 'FAKE CONSOLE OUTPUT\nANOTHER\nLAST LINE'

    def get_vnc_console(self, context, instance):
        LOG.debug("get_vnc_console")

    def get_spice_console(self, context, instance):
        LOG.debug("get_spice_console")

    def get_rdp_console(self, context, instance):
        LOG.debug("get_rdp_console")

    def get_serial_console(self, context, instance):
        LOG.debug("get_serial_console")

    def get_console_pool_info(self, console_type):
        LOG.debug("get_console_pool_info")

    def refresh_security_group_rules(self, security_group_id):
        LOG.debug("refresh_security_group_rules")
        return True

    def refresh_security_group_members(self, security_group_id):
        LOG.debug("refresh_security_group_members")
        return True

    def refresh_instance_security_rules(self, instance):
        LOG.debug("refresh_instance_security_rules")
        return True

    def refresh_provider_fw_rules(self):
        LOG.debug("refresh_provider_fw_rules")

    def get_available_resource(self, nodename):
        LOG.debug("get_available_resource")
        return {'vcpus': 32,
                'memory_mb': 164403,
                'local_gb': 5585,
                'vcpus_used': 0,
                'memory_mb_used': 10,
                'local_gb_used': 3,
                'hypervisor_type': 'vcloud',
                'hypervisor_version': 5005000,
                'hypervisor_hostname': nodename,
                'cpu_info':
                    '{"model": ["Intel(R) Xeon(R) CPU E5-2670 0 @ 2.60GHz"],'
                    '"vendor": ["Huawei Technologies Co., Ltd."],'
                    '"topology": {"cores": 16, "threads": 32}}',
                'supported_instances':
                    [(arch.I686, hv_type.BAREMETAL, vm_mode.HVM),
                     (arch.X86_64, hv_type.BAREMETAL, vm_mode.HVM),
                     (arch.I686, hv_type.LXC, vm_mode.HVM),
                     (arch.X86_64, hv_type.LXC, vm_mode.HVM),
                     (arch.I686, hv_type.LXD, vm_mode.HVM),
                     (arch.X86_64, hv_type.LXD, vm_mode.HVM)],
                'numa_topology': None,
                }

    def ensure_filtering_rules_for_instance(self, instance_ref, network_info):
        LOG.debug("ensure_filtering_rules_for_instance")

    def get_instance_disk_info(self, instance_name, block_device_info=None):
        LOG.debug("get_instance_disk_info")

    def live_migration(self, context, instance_ref, dest,
                       post_method, recover_method, block_migration=False,
                       migrate_data=None):
        LOG.debug("live_migration")

    def check_can_live_migrate_destination_cleanup(self, ctxt,
                                                   dest_check_data):
        LOG.debug("check_can_live_migrate_destination_cleanup")

    def check_can_live_migrate_destination(self, ctxt, instance_ref,
                                           src_compute_info, dst_compute_info,
                                           block_migration=False,
                                           disk_over_commit=False):
        LOG.debug("check_can_live_migrate_destination")
        return {}

    def check_can_live_migrate_source(self, ctxt, instance_ref,
                                      dest_check_data):
        LOG.debug("check_can_live_migrate_source")

    def finish_migration(self, context, migration, instance, disk_info,
                         network_info, image_meta, resize_instance,
                         block_device_info=None, power_on=True):
        LOG.debug("finish_migration")

    def confirm_migration(self, migration, instance, network_info):
        LOG.debug("confirm_migration")

    def pre_live_migration(self, context, instance_ref, block_device_info,
                           network_info, disk, migrate_data=None):
        LOG.debug("pre_live_migration")

    def unfilter_instance(self, instance_ref, network_info):
        LOG.debug("unfilter_instance")

    def get_host_stats(self, refresh=False):
        LOG.debug("get_host_stats")

    def host_power_action(self, host, action):
        LOG.debug("host_power_action")
        return action

    def host_maintenance_mode(self, host, mode):
        LOG.debug("host_maintenance_mode")
        if not mode:
            return 'off_maintenance'
        return 'on_maintenance'

    def set_host_enabled(self, host, enabled):
        LOG.debug("set_host_enabled")
        if enabled:
            return 'enabled'
        return 'disabled'

    def get_volume_connector(self, instance):
        LOG.debug("get_volume_connector")
        return {'ip': '127.0.0.1', 'initiator': 'fake', 'host': 'fakehost'}

    def get_available_nodes(self, refresh=False):
        LOG.debug("get_available_nodes")
        return {}

    def instance_on_disk(self, instance):
        LOG.debug("instance_on_disk")
        return False

    def volume_snapshot_create(self, context, instance, volume_id,
                               create_info):
        LOG.debug("volume_snapshot_create")

    def volume_snapshot_delete(self, context, instance, volume_id,
                               snapshot_id, delete_info):

        LOG.debug("volume_snapshot_delete")

    def change_instance_metadata(self, context, instance, diff):
        LOG.debug("change_instance_metadata")

    def get_info(self, instance):
        state = power_state.NOSTATE
        try:
            vm_name = self._get_vm_name(instance)
            state = self._provider_client.get_vm_status(instance, vm_name)
        except Exception as e:
            LOG.info('can not get info for VM %s: %s' % (instance.uuid, e))

        return hardware.InstanceInfo(
            state=state,
            max_mem_kb=0,
            mem_kb=0,
            num_cpu=1,
            cpu_time_ns=0
        )

    def plug_vifs(self,
                  context,
                  instance,
                  network_info,
                  provider_mgnt_ip,
                  provider_data_ip):
        LOG.debug("plug_vifs")
        neutron = neutronapi.get_client(context, admin=True)
        for vif in network_info:
            neutron.update_port(vif['id'],
                                {'port': {
                                    'binding:host_id': instance.uuid,
                                    'binding:profile': {
                                        'provider_mgnt_ip': provider_mgnt_ip,
                                        'provider_data_ip': provider_data_ip,
                                    }
                                }})

    def unplug_vifs(self, instance, network_info):
        LOG.debug("unplug_vifs")

    def _get_vm_name(self, instance):
        vm_naming_rule = cfg.CONF.hybrid_driver.vm_naming_rule
        if vm_naming_rule == 'openstack_vm_id':
            return instance.uuid
        elif vm_naming_rule == 'openstack_vm_name':
            return instance.display_name
        elif vm_naming_rule == 'cascaded_openstack_rule':
            return instance.display_name
        else:
            return instance.uuid

    def _update_md(self, instance, network_info, nets_conf):
        # set the provider ips in instance metadata
        md = dict(instance.metadata)
        md_changed = False

        for net_conf in nets_conf:
            if 'neutron_id' in net_conf:
                neutron_id = net_conf['neutron_id']
                ip = None
                if 'ip' in net_conf:
                    ip = net_conf['ip']
                if 'external_ip' in net_conf:
                    ip = net_conf['external_ip']
                if ip:
                    md_changed = True
                    md['provider_ip'] = ip
                    for vif in network_info:
                        if vif['id'] == neutron_id:
                            md['ip_%s' % ip] = vif.get('id')
                            break
        if md_changed:
            instance.metadata = md
            instance.save()
