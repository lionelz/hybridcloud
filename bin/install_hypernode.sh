#!/bin/bash

# TODO....
FROM_DIR=/root/hyperagent

rm -rf /usr/lib/python2.7/dist-packages/hyperagent*
cp -r $FROM_DIR/hyperagent /usr/lib/python2.7/dist-packages
cp -r $FROM_DIR/hyperagent.egg-info /usr/lib/python2.7/dist-packages/hyperagent-0.0.2.egg-info

rm -f /usr/bin/hyper-agent-*
cp $FROM_DIR/bin/hyper-agent-* /usr/bin

rm -f /etc/init/hyper-agent-*.conf
cp $FROM_DIR/etc/init/hyper-agent-*.conf /etc/init

rm -rf /etc/hyperagent
cp -r $FROM_DIR/etc/hyperagent /etc

rm -rf /var/log/hyperagent
mkdir /var/log/hyperagent
