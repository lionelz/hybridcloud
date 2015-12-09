#!/bin/bash

# TODO....
FROM_DIR=/root/hybridcloud

rm -rf /usr/lib/python2.7/dist-packages/hybridcloud*
cp -r $FROM_DIR/hybridcloud /usr/lib/python2.7/dist-packages
cp -r $FROM_DIR/hybridcloud.egg-info /usr/lib/python2.7/dist-packages/hybridcloud-0.0.1.egg-info

rm -f /usr/bin/hyper-agent-*
cp $FROM_DIR/bin/hyper-agent-* /usr/bin

rm -f /etc/init/hyper-agent-*.conf
cp $FROM_DIR/etc/init/hyper-agent-*.conf /etc/init

rm -rf /etc/hybridcloud
cp -r $FROM_DIR/etc/hybridcloud /etc

rm -rf /var/log/hybridcloud
mkdir /var/log/hybridcloud
