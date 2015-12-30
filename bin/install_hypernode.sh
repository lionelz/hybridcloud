#!/bin/bash
set -x

# run common
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
$DIR/install_common.sh

rm -f /usr/bin/hypervm-config

rm -f /etc/init/hypervm-config.conf
rm -f /etc/init/hyper-agent-cleanup.conf 
cp $FROM_DIR/etc/init/hyper-agent-cleanup.conf.hypervm /etc/init/hyper-agent-cleanup.conf


rm /etc/hybridcloud/hyper-agent.conf.hypernode.tmpl
mv /etc/hybridcloud/hyper-agent.conf.hypervm.tmpl /etc/hybridcloud/hyper-agent.conf.tmpl
