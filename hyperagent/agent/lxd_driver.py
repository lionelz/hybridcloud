from hyperagent.agent import hyper_agent_utils as hu


class API(object):

    def __init__(self):
        pass

    def container_init(self, container_config):
        cmd = ['lxc', 'init',
               container_config['source']['alias'],
               container_config['name']]
        kwargs = {'run_as_root': True}
        for profile in container_config['profiles']:
            cmd += ['-p', profile]
        hu.execute(*cmd, **kwargs)

    def destroy(self, name, timeout):
        hu.execute('lxc', 'delete', name,
                   check_exit_code=False,
                   run_as_root=True)

    def start(self, name, timeout):
        hu.execute('lxc', 'start',
                   name, run_as_root=True)

    def stop(self, name):
        hu.execute('lxc', 'stop',
                   name, run_as_root=True)

    def container_update(self, name, config):
        for eth, props in config['devices'].iteritems():
            cmd = ['lxc', 'config', 'device',
                   'add', name, eth, props['type']]
            kwargs = {'run_as_root': True}
            for k, v in props.iteritems():
                if k != 'type':
                    cmd += ['%s=%s' % (k, v)] 
            hu.execute(*cmd, **kwargs)

    def profile_create(self, profile):
        hu.execute('lxc', 'profile', 'delete',
                   profile['name'],
                   check_exit_code=False,
                   run_as_root=True)
        hu.execute('lxc', 'profile', 'create',
                   profile['name'], 
                   run_as_root=True)
        for k, v in profile['config'].iteritems():
            hu.execute('lxc', 'profile', 'set',
                       profile['name'],
                       k, v, 
                       run_as_root=True)


if __name__ == "__main__":
    lxd = API()
    null_profile = { 'config':{}, 'name': 'null_profile'}
    lxd.profile_create(null_profile)
    print('profile created')
    container_info =  {'alias': 'trusty'}
    container_name = "s123456"
    lxd.destroy(container_name, 100)
    container_alias = container_info['alias']
    container_config = {'name': container_name, 'profiles': ['null_profile'],
                        'source': { 'type': 'image', 'alias':container_alias } } 
    lxd.container_init(container_config)
    print('container initted')
    hu.execute('ip', 'link', 'add', 'vvv1', 'type', 'veth',
               'peer', 'name', 'vvv2', check_exit_code=False)
    for dev in ['vvv1', 'vvv2']:
        hu.execute('ip', 'link', 'set', dev, 'up')

    eth_vif_config = {'devices': 
                        { 'eth0':
                            { 'type':'nic',
                              'nictype': 'physical',
                              'parent': 'vvv2'  
                            }
                        }
                     }
    lxd.container_update(container_name, eth_vif_config)
    print('container updated')
    lxd.start(container_name, 100)
    print('container started')
    lxd.stop(container_name)
    print('container stopped')
    lxd.destroy(container_name, 100)
    print('container destroyed')
