from hyperagent.agent import hyper_agent_utils as hu


class API(object):

    run_as_root = True

    def __init__(self):
        pass

    def _execute(self, *cmd, **kwargs):
        if API.run_as_root:
            kwargs['run_as_root'] = True
        return hu.execute(*cmd, **kwargs)

    # images
    def image_defined(self, image):
        defined = False
        cli_output = self._execute('lxc', 'image', 'show', image,
                                   check_exit_code=False)[0]
        if cli_output and cli_output != '':
            defined = True
        return defined

    def image_upload(self, path=None, data=None, headers={}):
        self._execute('lxc', 'image', 'import',
                      path, '--alias=%s' % headers['alias'])

    # containers:
    def container_defined(self, container):
        defined = False
        cli_output = self._execute('lxc', 'info', container,
                                   check_exit_code=False)[0]
        if cli_output and cli_output != '':
            defined = True
        return defined

    def container_running(self, container):
        cli_output = self._execute('lxc', 'info', container,
                                   check_exit_code=False)[0]
        running = False
        if cli_output and cli_output != '':
            for line in cli_output.split('\n'):
                if 'Status:' in line and 'Running' in line:
                    running = True
        return running

    def container_init(self, container):
        cmd = ['lxc', 'init',
               container['source']['alias'],
               container['name']]
        kwargs = {}
        for profile in container['profiles']:
            cmd += ['-p', profile]
        self._execute(*cmd, **kwargs)

    def container_update(self, container, config):
        if 'config' in config:
            for k, v in config['config'].iteritems():
                self._execute('lxc', 'config', 'set', container, k, v)
        elif 'devices' not in config or len(config['devices']) == 0:
            for eth in [0, 10]:
                self._execute('lxc', 'config', 'device',
                              'remove', container, 'eth%d' % eth,
                              check_exit_code=False)
        else:
            for eth, props in config['devices'].iteritems():
                cmd = ['lxc', 'config', 'device',
                       'add', container, eth, props['type']]
                kwargs = {}
                for k, v in props.iteritems():
                    if k != 'type':
                        cmd += ['%s=%s' % (k, v)]
                self._execute(*cmd, **kwargs)

    def container_start(self, container, timeout):
        self._execute('lxc', 'start', container)

    def container_stop(self, container, timeout):
        self._execute('lxc', 'stop', container)

    def container_destroy(self, container):
        self._execute('lxc', 'delete', container, check_exit_code=False)

    # profiles
    def profile_create(self, profile):
        self._execute('lxc', 'profile', 'delete', profile['name'],
                      check_exit_code=False)
        self._execute('lxc', 'profile', 'create', profile['name'])
        for k, v in profile['config'].iteritems():
            self._execute('lxc', 'profile', 'set', profile['name'], k, v)


if __name__ == "__main__":
    lxd = API()
    API.run_as_root = False
    null_profile = {'config': {}, 'name': 'null_profile'}
    lxd.profile_create(null_profile)
    print('profile created')
    container_info = {'alias': 'trusty'}
    container = "s123456"
    lxd.container_destroy(container)
    container_alias = container_info['alias']
    container_config = {
        'name': container,
        'profiles': ['null_profile'],
        'source': {'type': 'image', 'alias': container_alias}
    }
    if lxd.container_defined(container):
        print ('container %s is defined' % container)
    else:
        print ('container %s is not defined' % container)
    if lxd.container_running(container):
        print ('container %s is running' % container)
    else:
        print ('container %s is not running' % container)
    lxd.container_init(container_config)
    if lxd.container_defined(container):
        print ('container %s is defined' % container)
    else:
        print ('container %s is not defined' % container)
    print('container initialized')
    hu.execute('ip', 'link', 'add', 'vvv1', 'type', 'veth',
               'peer', 'name', 'vvv2', check_exit_code=False)
    for dev in ['vvv1', 'vvv2']:
        hu.execute('ip', 'link', 'set', dev, 'up')

    eth_vif_config = {
        'devices': {
            'eth0': {
                'type': 'nic',
                'nictype': 'physical',
                'parent': 'vvv2'
            }
        }
    }

    lxd.container_update(container, eth_vif_config)
    print('container updated')
    if lxd.container_running(container):
        print ('container %s is running' % container)
    else:
        print ('container %s is not running' % container)
    lxd.container_start(container, 100)
    print('container started')
    if lxd.container_running(container):
        print ('container %s is running' % container)
    else:
        print ('container %s is not running' % container)
    lxd.container_stop(container, 100)
    print('container stopped')
    lxd.container_destroy(container)
    print('container destroyed')
    if lxd.container_defined(container):
        print ('container %s is defined' % container)
    else:
        print ('container %s is not defined' % container)
