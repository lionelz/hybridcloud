# Hybrid Cloud sample code project for vCloud and AWS 

## Devstack all-in-one installation with vcloud nova driver

1. Based on ubuntu server 14.04 installation
2. get devstack, juno version (eol)
```
    git clone https://github.com/openstack-dev/devstack.git
    cd devstack
    git checkout juno-eol
```
3. get hybroudcloud code
```
    cd /opt/stack
    git clone https://github.com/lionelz/hybridcloud.git
```
4. Install pyvcloud version 10

```
    sudo pip install pyvcloud==10
```

5. install ovftool

6. local.conf configuration sample

```
[[local|localrc]]
HOST_IP=##your data interface host ip##

ADMIN_PASSWORD=stack
DATABASE_PASSWORD=$ADMIN_PASSWORD
RABBIT_PASSWORD=$ADMIN_PASSWORD
SERVICE_PASSWORD=$ADMIN_PASSWORD
SERVICE_TOKEN=## unique service token##

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
disable_service tempest

CEILOMETER_BRANCH=juno-eol
CINDER_BRANCH=juno-eol
GLANCE_BRANCH=juno-eol
HEAT_BRANCH=juno-eol
HORIZON_BRANCH=juno-eol
IRONIC_BRANCH=juno-eol
KEYSTONE_BRANCH=juno-eol
NEUTRON_BRANCH=juno-eol
NOVA_BRANCH=juno-eol
SAHARA_BRANCH=juno-eol
SWIFT_BRANCH=juno-eol
TROVE_BRANCH=juno-eol
REQUIREMENTS_BRANCH=juno-eol

[[post-config|/$Q_PLUGIN_CONF_FILE]]
[vxlan]
enable_vxlan = True
local_ip = ##your managment interface host ip##


[[post-config|$NOVA_CONF]]
[DEFAULT]
compute_driver = nova_driver.virt.hybrid.VCloudDriver
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

7. copy the base-1.vmx file to /opt/stack/data/hybridcloud/vmx

 
## Agent VM creation based on ubuntu 14.04
1. add juno openstack repository
2. install neutron agent
3. install nova code
4. Hybrid code and install
    sudo apt-get install git

## TODO: Devstack all-in-one installation with AWS nova driver


