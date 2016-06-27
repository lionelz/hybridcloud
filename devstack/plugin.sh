# check for service enabled
if [[ "$1" == "stack" && "$2" == "pre-install" ]]; then
    :
elif [[ "$1" == "stack" && "$2" == "install" ]]; then
    # Perform installation of service source
    echo_summary "Installing 3rd parties"
    sudo apt-get install libz-dev libxml2-dev libxslt1-dev
    sudo pip install boto3
    sudo pip install pyvcloud
elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
    mkdir -p /opt/stack/data/hybridcloud/vmx
    cp /opt/stack/hybridcloud/etc/hybridcloud/base-template.vmx /opt/stack/data/hybridcloud/vmx
    echo export PYTHONPATH=\$PYTHONPATH:/opt/stack/hybridcloud>> $RC_DIR/.localrc.auto 
elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
    :
elif [[ "$1" == "unstack" ]]; then
    :
elif [[ "$1" == "clean" ]]; then
    :
fi
