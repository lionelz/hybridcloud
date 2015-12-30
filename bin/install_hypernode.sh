#!/bin/bash
set -x

# run common
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
$DIR/install_common.sh

rm -f /etc/init/hypernode-config.conf
rm -f /etc/init/hyper-agent-cleanup.conf 
cp $FROM_DIR/etc/init/hyper-agent-cleanup.conf.hypernode /etc/init/hyper-agent-cleanup.conf


rm /etc/hybridcloud/hyper-agent.conf.hypervm.tmpl
mv /etc/hybridcloud/hyper-agent.conf.hypernode.tmpl /etc/hybridcloud/hyper-agent.conf.tmpl
