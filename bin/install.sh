#!/bin/bash
set -x

# based on ubuntu 14.04.03
# set 3 manual network interfaces
# manual sysctl configuration
# set in /etc/sysctl.conf
# edit_sysctl net.ipv4.conf.all.rp_filter 0
# edit_sysctl net.ipv4.conf.default.rp_filter 0
# sysctl -p

# install the nova/neutron packages
add-apt-repository -y cloud-archive:liberty
apt-get -y update
apt-get -y dist-upgrade
apt-get --no-install-recommends -y install neutron-plugin-openvswitch neutron-plugin-openvswitch-agent neutron-l3-agent

apt-get -y install bridge-utils openvpn easy-rsa python-ryu
apt-get --no-install-recommends -y install python-nova
apt-get -y install open-vm-tools iperf3 open-vm-dkms

ovs-vsctl --may-exist add-br br-ex

#remove automatic openvpn start
update-rc.d openvpn disable

FROM_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/.."
PYTHON_PKG_DIR=/usr/lib/python2.7/dist-packages

# hyper agent python packages
rm -rf $PYTHON_PKG_DIR/hyperagent
rm -rf $PYTHON_PKG_DIR/hyperagent-info
cp -r $FROM_DIR/hyperagent $PYTHON_PKG_DIR
cp -r $FROM_DIR/hyperagent.egg-info $PYTHON_PKG_DIR/hyperagent-0.0.4.egg-info

# binaries
bin_files='hyper-agent hyper-agent-cleanup hyper-agent-rootwrap hypervm-config'
for f in $bin_files
do
    rm -f /usr/bin/$f
    cp $FROM_DIR/bin/$f /usr/bin
done

# init conf
rm -f /etc/init/hyper*
cp -r $FROM_DIR/etc/init/* /etc/init

# etc hyper-agent conf
rm -rf /etc/hybridcloud
cp -r $FROM_DIR/etc/hybridcloud /etc

# neutron template
rm -rf `find /etc/neutron -name "*.tmpl"`
cp $FROM_DIR/etc/neutron/l3_agent.conf.tmpl /etc/neutron
cp $FROM_DIR/etc/neutron/neutron.conf.tmpl /etc/neutron
cp $FROM_DIR/etc/neutron/plugins/ml2/ml2_conf.ini.tmpl /etc/neutron/plugins/ml2
cp $FROM_DIR/etc/neutron/plugins/ml2/openvswitch_agent.ini.tmpl /etc/neutron/plugins/ml2

# var folder
rm -rf /var/log/hybridcloud
rm -rf /var/log/upstart/*
mkdir /var/log/hybridcloud

# clean
apt-get clean
rm -f /var/lib/apt/lists/*
cat /dev/zero > zero
rm -f zero
