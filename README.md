# Hybrid Cloud Connectivity Sample Code 

## Devstack all-in-one installation with vcloud nova driver

- Based on ubuntu server 14.04 installation
- intialy update apt database
```
sudo apt-get update && apt-get upgrade
```
- Install git 
```
sudo apt-get install git
```

- get devstack, liberty version
```
git clone https://github.com/openstack-dev/devstack.git
cd devstack
git checkout stable/liberty
./stack.sh (stop it Ctrl-C after pip installation)
```
- get hybridcloud code
```
cd /opt/stack
git clone https://github.com/lionelz/hybridcloud.git
```
- Install pyvcloud 
```
sudo apt-get install libz-dev libxml2-dev libxslt1-dev
sudo pip install pyvcloud
```
- Install boto3 for aws access 
```
sudo pip install boto3
```
- install ovftool (tools/VMware-ovftool-4.1.0-2459827-lin.x86_64.bundle)
```
sh /opt/stack/hybridcloud/tools/VMware-ovftool-4.1.0-2459827-lin.x86_64.bundle
```
- Add in the PYTHONPATH the folder /opt/stack/hybridcloud
```
Add in the file ~/.bashrc add at the end:
export PYTHONPATH=/opt/stack/hybridcloud
```
- copy the base-template.vmx file to the folder /opt/stack/data/hybridcloud/vmx
```
mkdir /opt/stack/data/hybridcloud
mkdir /opt/stack/data/hybridcloud/vmx
cp /opt/stack/hybridcloud/etc/hybridcloud/base-template.vmx /opt/stack/data/hybridcloud/vmx 
```
- local.conf configuration sample
```
[[local|localrc]]
HOST_IP=##your mgmt interface host ip##
LOGFILE=$DEST/logs/stack.sh.log

ADMIN_PASSWORD=stack
DATABASE_PASSWORD=$ADMIN_PASSWORD
RABBIT_PASSWORD=$ADMIN_PASSWORD
SERVICE_PASSWORD=$ADMIN_PASSWORD
SERVICE_TOKEN=$ADMIN_PASSWORD

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

[[post-config|/$Q_PLUGIN_CONF_FILE]]
[vxlan]
enable_vxlan = True
local_ip = ##your data interface host ip##
[ovs]
enable_tunneling = True
local_ip = ##your data interface host ip##

[[post-config|$NOVA_CONF]]
[DEFAULT]
compute_driver = nova_driver.virt.hybrid.HybridDriver

[hybrid_driver]
provider = ###aws or vcloud###
conversion_dir = /opt/stack/data/hybridcloud
volumes_dir = /opt/stack/data/hybridcloud
vm_naming_rule = openstack_vm_id

[aws]
access_key_id = ## AWS access key id ##
secret_access_key = ## AWS access key secret ##
region_name = ## region name ##
s3_bucket_tmp = ## s3 tmp bucket for image upload ##
flavor_map = m1.nano:t2.micro, m1.micro:t2.micro, m1.tiny:t2.micro, m1.small:t2.micro, m1.medium:t2.micro, m1.large:t2.micro, m1.xlarge:t2.micro
security_group_mgnt_network = ## mgmt security group id subnet ##
mgnt_network = ##name of mgmt net or id##
security_group_data_network = ## data security group id subnet ##
data_network = ##name of data net or id##

[vcloud]
node_name = ##node description name##
host_ip = ##vcloud ip##
host_username = ##vcloud user##
host_password = ##vcloud password##
vdc = ##vcloud vdc##
org = ##vcloud org##
flavor_map = m1.nano:1, m1.micro:1, m1.tiny:1, m1.small:1, m1.medium:1, m1.large:1, m1.xlarge:1
metadata_iso_catalog = metadata-isos
mgnt_network = ##name of mgmt net or id##
data_network = ##name of data net or id##
``` 
- Run stack script
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
