# Hybrid Cloud sample code project for vCloud and AWS 

## devstack all in one installation with vcloud nova driver

1. Based on ubuntu server 14.04 installation

2. get devstack, juno version

     git clone https://github.com/openstack-dev/devstack.git -b stable/juno

3. local.conf configuration sample

```
[[local|localrc]]

HOST_IP=##your host ip##

ADMIN_PASSWORD=stack
DATABASE_PASSWORD=$ADMIN_PASSWORD
RABBIT_PASSWORD=$ADMIN_PASSWORD
SERVICE_PASSWORD=$ADMIN_PASSWORD
SERVICE_TOKEN=a682f596-76f3-11e3-b3b2-e716f9080d50

disable_service n-net
enable_service q-svc
enable_service q-agt
enable_service q-dhcp
enable_service q-l3
enable_service q-meta
enable_service neutron
enable_service n-novnc
enable_service n-cauth
disable_service h-eng
disable_service h-api
disable_service h-api-cfn
disable_service h-api-cw

enable_plugin hybridcloud https://github.com/lionelz/hybridcloud


[[post-config|$NOVA_CONF]]
[DEFAULT]
compute_driver = nova.virt.hybrid.VCloudDriver

[vcloud]
vcloud_conversion_dir = /opt/stack/data/hybridcloud
vcloud_volumes_dir = /opt/stack/data/hybridcloud
vcloud_host_ip = ##vcloud ip##
vcloud_vdc = ##vcloud vdc##
vcloud_org = ##vcloud org##
vcloud_host_username = ##vcloud user##
vcloud_host_password = ##vcloud password##
vcloud_vm_naming_rule = openstack_vm_id
vcloud_flavor_map =  m1.nano:1, m1.micro:1, m1.tiny:1, m1.small:1, m1.medium:1, m1.large:1, m1.xlarge:1
vcloud_node_name = ##node description name##
provider_api_network_name = api-network
provider_tunnel_network_name = data-network
```

# agent installation for ubuntu 14.04
1. add juno openstack repository
2. install neutron agent
3. install nova code
4. git code + install
    sudo apt-get install git

