losetup /dev/loop0 /opt/stack/data/stack-volumes-default-backing-file
losetup /dev/loop1 /opt/stack/data/stack-volumes-lvmdriver-1-backing-file
ifconfig br-ex 172.24.4.1 netmask 255.255.255.0
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE