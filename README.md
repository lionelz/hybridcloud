# Hybrid Cloud Connectivity Sample Code 

## Devstack all-in-one installation with vcloud nova driver

- Based on ubuntu server 14.04 installation
- get devstack, juno version (eol)
```
    git clone https://github.com/openstack-dev/devstack.git
    cd devstack
    git checkout juno-eol
```
- get hybroudcloud code
```
    cd /opt/stack
    git clone https://github.com/lionelz/hybridcloud.git
```
- copy the base-1.vmx file to the folder /opt/stack/data/hybridcloud/vmx
- Install pyvcloud version 10
```
    sudo pip install pyvcloud==10
```
- install ovftool
- local.conf configuration sample
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
 
## Agent VM creation
- Based on ubuntu 14.04
- Edit the /etc/sysctl.conf file to contain the following parameters:
```
    net.ipv4.conf.all.rp_filter=0
    net.ipv4.conf.default.rp_filter=0
```
- Implement the changes:
```
    sudo sysctl -p
```
- add juno openstack repository
```
    sudo add-apt-repository cloud-archive:juno
```
- install neutron agent
```
    sudo apt-get --no-install-recommends -y install neutron-plugin-ml2 neutron-plugin-openvswitch-agent
```
- install nova code
```
    sudo apt-get --no-install-recommends -y install python-nova
```
- Hybrid code and install
```
    sudo apt-get install git
    git clone https://github.com/lionelz/hybridcloud.git
    cd hybridcloud/bin
    sudo ./install_hypervm.sh
```

## TODO: Devstack all-in-one installation with AWS nova driver


