# hybridcloud

# TODO: devstack with vcloud nova driver

1. get devstack, juno version
-----------------------------
     git clone https://github.com/openstack-dev/devstack.git -b stable/juno

2. local.conf configuration
---------------------------

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

[[post-config|$NOVA_CONF]]
[DEFAULT]
compute_driver = nova.virt.hybrid.VCloudDriver



# agent installation for ubuntu 14.04
1. add juno openstack repository
2. install neutron agent
3. install nova code
4. git code + install
    sudo apt-get install git

