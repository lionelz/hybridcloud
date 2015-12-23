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
- Install pyvcloud version 10 
     - must be run before the stack script
     - If pip is not installed, run the stack script and interrupt it after the pip command is installed  
```
sudo apt-get install libz-dev libxml2-dev libxslt1-dev python-dev
sudo pip install pyvcloud==10
```
- Install boto3 for aws access 
```
sudo pip install pyvcloud==10
```
- install ovftool (tools/VMware-ovftool-4.1.0-2459827-lin.x86_64.bundle)
```
sh tools/VMware-ovftool-4.1.0-2459827-lin.x86_64.bundle
```
- Add in the PYTHONPATH the folder /opt/stack/hybridcloud
```
Add in the file ~/.bashrc add at the end:
export PYTHONPATH=/opt/stack/hybridcloud
```
- local.conf configuration sample
```
[[local|localrc]]
HOST_IP=##your data interface host ip##
LOGFILE=$DEST/logs/stack.sh.log

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
compute_driver = nova_driver.virt.hybrid.HybridDriver

[hybrid_driver]
provider = aws or vcloud
conversion_dir = /opt/stack/data/hybridcloud
volumes_dir = /opt/stack/data/hybridcloud
vm_naming_rule = openstack_vm_id
provider_mgnt_network = ##name of mgmt net or id##
provider_data_network = ##name of data net or id##

[aws]
access_key_id = ## AWS access key id ##
secret_access_key = ## AWS access key secret ##
region_name = ## region name ##
s3_bucket_tmp = ## s3 tmp bucket for image upload ##
flavor_map = m1.nano:t2.micro, m1.micro:t2.micro, m1.tiny:t2.micro, m1.small:t2.micro, m1.medium:t2.micro, m1.large:t2.micro, m1.xlarge:t2.micro
security_group_mgnt_network = ## mgmt security group id subnet ##
security_group_data_network = ## data security group id subnet ##

[vcloud]
node_name=##node description name##
host_ip = ##vcloud ip##
host_username = ##vcloud user##
host_password = ##vcloud password##
vdc = ##vcloud vdc##
org = ##vcloud org##
flavor_map = m1.nano:1, m1.micro:1, m1.tiny:1, m1.small:1, m1.medium:1, m1.large:1, m1.xlarge:1
metadata_iso_catalog = metadata-isos
```
- copy the base-1.vmx file to the folder /opt/stack/data/hybridcloud/vmx
- copy the base-aws.vmx file to the folder /opt/stack/data/hybridcloud/vmx
```
mkdir /opt/stack/data/hybridcloud
mkdir /opt/stack/data/hybridcloud/vmx
cp /opt/stack/hybridcloud/etc/hybridcloud/base-1.vmx /opt/stack/data/hybridcloud/vmx 
cp /opt/stack/hybridcloud/etc/hybridcloud/base-aws.vmx /opt/stack/data/hybridcloud/vmx 
```
- TROUBLESHOOTING: oslo.utils package version must be 1.4.1
```
sudo pip uninstall oslo.utils
sudo pip install oslo.utils==1.4.1
``` 
- Install openstack
``` 
cd ~/devstack && ./stack.sh
``` 

## Agent VM creation
- Based on ubuntu 14.04
- Hybrid code and thirdparties install
```
sudo apt-get install git
git clone https://github.com/lionelz/hybridcloud.git
cd hybridcloud
sudo ./bin/install_hypervm.sh
```


