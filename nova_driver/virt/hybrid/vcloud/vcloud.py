# VMware vCloud Python helper
# Copyright (c) 2014 Huawei, Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at #
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from nova import exception
from nova.i18n import _LW
from oslo_concurrency import lockutils
from oslo_log import log as logging
from oslo_service import loopingcall
from pyvcloud.vcloudair import VCA
from threading import Lock

LOG = logging.getLogger(__name__)


class VCloudAPISession(object):

    """Sets up a session with the vcloud and handles all
    the calls made to the vcloud.
    """

    def __init__(self, host_ip, host_port, server_username, server_password,
                 org, vdc, version, verify, service_type,
                 retry_count, create_session=True, scheme="https",
                 task_poll_interval=1):
        self._host_ip = host_ip
        self._server_username = server_username
        self._server_password = server_password
        self._org = org
        self._vdc = vdc
        self._version = version
        self._verify = verify
        self._service_type = service_type
        self._retry_count = retry_count
        self._scheme = scheme
        self._host_port = host_port
        self._session_username = None
        self._session_id = None
        self._vca = None
        self._task_poll_interval = task_poll_interval
        self._auto_lock = Lock()
        if create_session:
            self._create_session()

    @lockutils.synchronized('hypernode-plug-unplug')
    def _create_session(self):
        """Establish session with the server."""

        if self._session_id and self.is_current_session_active():
            LOG.debug("Current session: %s is active.",
                      self._session_id)
            return

        # Login and create new session with the server for making API calls.
        LOG.debug("Logging in with username = %s.", self._server_username)
        result = self.vca.login(password=self._server_password, org=self._org)
        if not result:
            raise exception.NovaException(
                "Logging error with username:%s " % self._server_username)
        result = self.vca.login(
            token=self.vca.token,
            org=self._org,
            org_url=self.vca.vcloud_session.org_url)
        if not result:
            raise exception.NovaException(
                "Logging error with username:%s with token " %
                self._server_username)

        self._session_id = self.vca.token

        # We need to save the username in the session since we may need it
        # later to check active session. The SessionIsActive method requires
        # the username parameter to be exactly same as that in the session
        # object. We can't use the username used for login since the Login
        # method ignores the case.
        self._session_username = self.vca.username
        LOG.info("Successfully established new session; session ID is %s.",
                 self._session_id)

    def is_current_session_active(self):
        """Check if current session is active.

        :returns: True if the session is active; False otherwise
        """
        LOG.debug("Checking if the current session: %s is active.",
                  self._session_id)

        is_active = False
        try:
            is_active = self.vca.session_is_active()
        except Exception:
            LOG.error("Check session is active error %s." % self._session_id,
                      exc_info=True)

        return is_active

    def invoke_api(self, module, method, *args, **kwargs):
        """Wrapper method for invoking APIs.

        The API call is retried in the event of exceptions due to session
        overload or connection problems.

        :param module: module corresponding to the VCA API call
        :param method: method in the module which corresponds to the
                       VCA API call
        :param args: arguments to the method
        :param kwargs: keyword arguments to the method
        :returns: response from the API call
        :raises: VCloudDriverException
        """
        @loopingcall.RetryDecorator(max_retry_count=self._retry_count)
        def _invoke_api(module, method, *args, **kwargs):
            try:
                api_method = getattr(module, method)
                return api_method(*args, **kwargs)
            except exception as excep:
                # If this is due to an inactive session, we should re-create
                # the session and retry.
                if self.is_current_session_active():
                    excep_msg = "VCloud connect error while invoking method "\
                        "%s.%s." % (module, method)
                    LOG.error(excep_msg, exc_info=True)
                    raise exception.NovaException(excep_msg)
                else:
                    LOG.warn(_LW("Re-creating session due to connection "
                                 "problems while invoking method "
                                 "%(module)s.%(method)s."),
                             {'module': module,
                              'method': method},
                             exc_info=True)
                    self._create_session()
                    raise excep

        return _invoke_api(module, method, *args, **kwargs)

    @property
    def vca(self):
        if not self._vca:
            self._vca = VCA(host=self._host_ip, username=self._server_username,
                            service_type=self._service_type,
                            version=self._version,
                            verify=self._verify)
        return self._vca

    @property
    def vdc(self):
        return self._vdc

    @property
    def username(self):
        return self._server_username

    @property
    def password(self):
        return self._server_password

    @property
    def host_ip(self):
        return self._host_ip

    @property
    def host_port(self):
        return self._host_port

    @property
    def org(self):
        return self._org
