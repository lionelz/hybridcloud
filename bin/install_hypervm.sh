#!/bin/bash
set -x

# check sysctl configuration

edit_sysctl () {
    TARGET_KEY=$1
    REPLACEMENT_VALUE=$2
    CONFIG_FILE=/etc/sysctl.conf
    if grep -q "^[ ^I]*$TARGET_KEY[ ^I]*=" "$CONFIG_FILE"; then
        sed -i -e "s^A^\\([ ^I]*$TARGET_KEY[ ^I]*=[ ^I]*\\).*$^A\\1$REPLACEMENT_VALUE^A" "$CONFIG_FILE"
    else
        echo "$TARGET_KEY = $REPLACEMENT_VALUE" >> "$CONFIG_FILE"
    fi
}

edit_sysctl(net.ipv4.conf.all.rp_filter,0)
edit_sysctl(net.ipv4.conf.default.rp_filter,0)
sysctl -p

# install the nova/neutron packages
add-apt-repository cloud-archive:juno
apt-get update
apt-get -y upgrade
apt-get -y dist-upgrade
apt-get --no-install-recommends -y install neutron-plugin-ml2 neutron-plugin-openvswitch-agent
apt-get --no-install-recommends -y install python-nova

FROM_DIR=`pwd`
PYTHON_PKG_DIR=/usr/lib/python2.7/dist-packages

# hyper agent python packages
rm -rf $PYTHON_PKG_DIR/hyperagent
rm -rf $PYTHON_PKG_DIR/hyperagent-info
cp -r $FROM_DIR/hyperagent $PYTHON_PKG_DIR
cp -r $FROM_DIR/hyperagent.egg-info $PYTHON_PKG_DIR/hyperagent-0.0.2.egg-info

# binaries
bin_files='hyper-agent hyper-agent-cleanup hyper-agent-rootwrap hypervm-config hypernode-config'
for f in $bin_files
do
    rm -f /usr/bin/$f
    cp $FROM_DIR/bin/$f /usr/bin
done
rm -f /usr/bin/hypernode-config

# init conf
init_conf_files='hyper-agent.conf hypervm-config.conf hypernode-config.conf'
for f in $init_conf_files
do
    rm -f /etc/init/$f
    cp $FROM_DIR/etc/init/$f /etc/init
done
rm -f /etc/init/hypernode-config.conf
rm -f /etc/init/hyper-agent-cleanup.conf 
cp $FROM_DIR/etc/init/hyper-agent-cleanup.conf.hypervm /etc/init/hyper-agent-cleanup.conf


# etc hyper-agent conf
rm -rf /etc/hybridcloud
cp -r $FROM_DIR/etc/hybridcloud /etc
rm /etc/hybridcloud/hyper-agent.conf.hypernode.tmpl
mv /etc/hybridcloud/hyper-agent.conf.hypervm.tmpl /etc/hybridcloud/hyper-agent.conf.tmpl

# neutron template
rm -rf `find /etc/neutron -name "*.tmpl"`
cp $FROM_DIR/etc/neutron/neutron.conf.tmpl /etc/neutron
cp $FROM_DIR/etc/neutron/plugins/ml2/ml2_conf.ini.tmpl /etc/neutron/plugins/ml2

# var folder
rm -rf /var/log/hybridcloud
mkdir /var/log/hybridcloud
