# encoding: utf-8

# Nagstamon - Nagios status monitor for your desktop
# Copyright (C) 2008-2014 Henri Wahl <h.wahl@ifw-dresden.de> et al.
# Thruk additions copyright by dcec@Github
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA

from Nagstamon.Servers.Generic import GenericServer
import sys
import json
import datetime
import copy
from collections import OrderedDict

from Nagstamon.Helpers import HumanReadableDurationFromTimestamp
from Nagstamon.Objects import (GenericHost, GenericService, Result)


class ThrukTomTomOSPServer(GenericServer):
    """
        ThrukTomTomOSP is derived from generic (Nagios) server
    """
    TYPE = 'ThrukTomTomOSP'

    # dictionary to translate status bitmaps on webinterface into status flags
    # this are defaults from Nagios
    # "disabled.gif" is in Nagios for hosts the same as "passiveonly.gif" for services
    STATUS_MAPPING = { "ack.gif" : "acknowledged", \
                       "passiveonly.gif" : "passiveonly", \
                       "disabled.gif" : "passiveonly", \
                       "ndisabled.gif" : "notifications_disabled", \
                       "downtime.gif" : "scheduled_downtime", \
                       "flapping.gif" : "flapping"}

    # Entries for monitor default actions in context menu
    MENU_ACTIONS = ["Monitor", "Recheck", "Acknowledge", "Submit check result", "Downtime"]

    # Arguments available for submitting check results
    SUBMIT_CHECK_RESULT_ARGS = ["check_output", "performance_data"]

    # URLs for browser shortlinks/buttons on popup window
    BROWSER_URLS = { "monitor": "$MONITOR$", \
                     "hosts": "$MONITOR-CGI$/status.cgi?hostgroup=all&style=hostdetail&hoststatustypes=12&page=1&entries=all&dfl_s0_value=tag%3AOSP-consumer-live", \
                     "services": "$MONITOR-CGI$/status.cgi?dfl_s0_value_sel=5&dfl_s0_servicestatustypes=29&dfl_s0_op=%3D&style=detail&dfl_s0_type=host&dfl_s0_serviceprops=0&dfl_s0_servicestatustype=4&dfl_s0_servicestatustype=8&dfl_s0_servicestatustype=16&dfl_s0_servicestatustype=1&hidetop=&dfl_s0_hoststatustypes=15&dfl_s0_val_pre=&hidesearch=2&dfl_s0_value=all&dfl_s0_hostprops=0&nav=&page=1&entries=all&dfl_s0_value=tag%3AOSP-consumer-live", \
                     "history": "$MONITOR-CGI$/history.cgi?host=all&page=1&entries=all"}

    STATES_MAPPING = {"hosts" : {0 : "OK", 1 : "DOWN", 2 : "UNREACHABLE"}, \
                      "services" : {0 : "OK", 1 : "WARNING", 2 : "CRITICAL", 3 : "UNKNOWN"}}


    def __init__(self, **kwds):
        GenericServer.__init__(self, **kwds)

        # flag for newer cookie authentication
        self.CookieAuth = False


    def reset_HTTP(self):
        """
            brute force reset by GenericServer disturbs logging in into Thruk
        """
        # only reset session if Thruks 2 cookies are there
        if len(self.session.cookies) > 1:
            self.session = None


    def init_HTTP(self):
        """
            partly not constantly working Basic Authorization requires extra Autorization headers,
            different between various server types
        """
        if self.session == None:
            GenericServer.init_HTTP(self)

        # only if cookies are needed
        if self.CookieAuth:
            # get cookie to access Thruk web interface
            # Thruk first send a test cookie, later an auth cookie
            if len(self.session.cookies) < 2:
                # get cookie from login page via url retrieving as with other urls
                try:
                    # login and get cookie
                    self.login()
                except:
                    self.Error(sys.exc_info())


    def init_config(self):
        """
            set URLs for CGI - they are static and there is no need to set them with every cycle
        """
        # create filters like described in
        # http://www.nagios-wiki.de/nagios/tips/host-_und_serviceproperties_fuer_status.cgi?s=servicestatustypes
        # Thruk allows requesting only needed information to reduce traffic
        self.cgiurl_services = self.monitor_cgi_url + "/status.cgi?nav=&entries=all&hidesearch=0&hidetop=&"\
                                                      "dfl_s0_hoststatustypes=15&dfl_s0_servicestatustypes=28&"\
                                                      "dfl_s0_hostprops=0&dfl_s0_serviceprops=0&style=detail&"\
                                                      "update.x=7&update.y=7&dfl_s0_type=search&dfl_s0_val_pre=&"\
                                                      "dfl_s0_op=%7E&dfl_s0_value=tag%3AOSP-consumer-live&"\
                                                      "dfl_s0_value_sel=5&dfl_s0_type=service&dfl_s0_val_pre=&"\
                                                      "dfl_s0_op=%21%7E&dfl_s0_value=DNS+Records&dfl_s0_value_sel=5&"\
                                                      "dfl_s0_type=service&dfl_s0_val_pre=&dfl_s0_op=%21%7E&"\
                                                      "dfl_s0_value=Patch+Management+-+Needs+Restarting&"\
                                                      "dfl_s0_value_sel=5&view_mode=json"
        # hosts (up or down or unreachable)
        self.cgiurl_hosts = self.monitor_cgi_url + "/status.cgi?nav=&entries=all&style=hostdetail&hidetop=&"\
                                                   "dfl_s0_hoststatustypes=12&dfl_s0_servicestatustypes=31&"\
                                                   "dfl_s0_hostprops=0&dfl_s0_serviceprops=0&style=hostdetail&"\
                                                   "update.x=8&update.y=11&dfl_s0_type=search&dfl_s0_val_pre=&"\
                                                   "dfl_s0_op=~&dfl_s0_value=tag%3AOSP-consumer-live&"\
                                                   "dfl_s0_value_sel=5&view_mode=json"


        # get cookie from login page via url retrieving as with other urls
        try:
            # login and get cookie
            if self.session == None:
                GenericServer.init_HTTP(self)

            self.login()

            if len(self.session.cookies) > 0:
                self.CookieAuth = True
        except:
            self.Error(sys.exc_info())


    def login(self):
        """
            use pure session instead of FetchURL to get Thruk session
        """
        self.session.post(self.monitor_cgi_url + '/login.cgi?',
                          data={'login': self.get_username(),
                                'password': self.get_password(),
                                'submit': 'Login',
                                'referer': ''})

    def _set_acknowledge(self, host, service, author, comment, sticky, notify, persistent, all_services=[]):
        '''
            send acknowledge to monitor server - might be different on every monitor type
        '''

        url = self.monitor_cgi_url + '/cmd.cgi'

        # the following flags apply to hosts and services
        #
        # according to sf.net bug #3304098 (https://sourceforge.net/tracker/?func=detail&atid=1101370&aid=3304098&group_id=236865)
        # the send_notification-flag must not exist if it is set to 'off', otherwise
        # the Nagios core interpretes it as set, regardless its real value
        #
        # for whatever silly reason Icinga depends on the correct order of submitted form items...
        # see sf.net bug 3428844
        #
        # Thanks to Icinga ORDER OF ARGUMENTS IS IMPORTANT HERE!
        #
        cgi_data = OrderedDict()
        if service == '':
            cgi_data['cmd_typ'] = '33'
        else:
            cgi_data['cmd_typ'] = '34'
        cgi_data['cmd_mod'] = '2'
        cgi_data['host'] = host
        if service != '':
            cgi_data['service'] = service
        cgi_data['com_author'] = author
        cgi_data['com_data'] = comment
        cgi_data['backend'] = '0ded1'

        cgi_data['btnSubmit'] = 'Commit'
        if notify == True:
            cgi_data['send_notification'] = 'on'
        if persistent == True:
            cgi_data['persistent'] = 'on'
        if sticky == True:
            cgi_data['sticky_ack'] = 'on'

        self.FetchURL(url, giveback='raw', cgi_data=cgi_data)

        # acknowledge all services on a host
        if len(all_services) > 0:
            for s in all_services:
                cgi_data['cmd_typ'] = '34'
                cgi_data['service'] = s
                self.FetchURL(url, giveback='raw', cgi_data=cgi_data)

    def _set_downtime(self, host, service, author, comment, fixed, start_time, end_time, hours, minutes):
        '''
            finally send downtime command to monitor server
        '''
        url = self.monitor_cgi_url + '/cmd.cgi'

        # for some reason Icinga is very fastidiuos about the order of CGI arguments, so please
        # here we go... it took DAYS :-(
        cgi_data = OrderedDict()
        if service == '':
            cgi_data['cmd_typ'] = '55'
        else:
            cgi_data['cmd_typ'] = '56'
        cgi_data['cmd_mod'] = '2'
        cgi_data['trigger'] = '0'
        cgi_data['host'] = host
        if service != '':
            cgi_data['service'] = service
        cgi_data['com_author'] = author
        cgi_data['com_data'] = comment
        cgi_data['fixed'] = fixed
        cgi_data['start_time'] = start_time
        cgi_data['end_time'] = end_time
        cgi_data['hours'] = hours
        cgi_data['minutes'] = minutes
        cgi_data['backend'] = '0ded1'
        cgi_data['btnSubmit'] = 'Commit'

        # running remote cgi command
        self.FetchURL(url, giveback='raw', cgi_data=cgi_data)




    def _get_status(self):
        """
            Get status from Thruk Server
        """
        # new_hosts dictionary
        self.new_hosts = dict()

        # hosts - mostly the down ones
        # unfortunately the hosts status page has a different structure so
        # hosts must be analyzed separately
        try:
            # JSON experiments
            result = self.FetchURL(self.cgiurl_hosts, giveback='raw')
            jsonraw, error, status_code = copy.deepcopy(result.result),\
                                          copy.deepcopy(result.error),\
                                          result.status_code

            # check if any error occured
            errors_occured = self.check_for_error(jsonraw, error, status_code)
            # if there are errors return them
            if errors_occured != False:
                return(errors_occured)

            # in case basic auth did not work try form login cookie based login
            if jsonraw.startswith("<"):
                self.CookieAuth = True
                return Result(result=None, error="Login failed")

            # in case JSON is not empty evaluate it
            elif not jsonraw == "[]":
                hosts = json.loads(jsonraw)

                for h in hosts:
                    if h["name"] not in self.new_hosts:
                        self.new_hosts[h["name"]] = GenericHost()
                        self.new_hosts[h["name"]].name = h["name"]
                        self.new_hosts[h["name"]].server = self.name
                        self.new_hosts[h["name"]].status = self.STATES_MAPPING["hosts"][h["state"]]
                        self.new_hosts[h["name"]].last_check = datetime.datetime.fromtimestamp(int(h["last_check"])).isoformat(" ")
                        self.new_hosts[h["name"]].duration = HumanReadableDurationFromTimestamp(h["last_state_change"])
                        self.new_hosts[h["name"]].attempt = "%s/%s" % (h["current_attempt"], h["max_check_attempts"])
                        self.new_hosts[h["name"]].status_information = h["plugin_output"].replace("\n", " ").strip()
                        self.new_hosts[h["name"]].passiveonly = not(bool(int(h["active_checks_enabled"])))
                        self.new_hosts[h["name"]].notifications_disabled = not(bool(int(h["notifications_enabled"])))
                        self.new_hosts[h["name"]].flapping = bool(int(h["is_flapping"]))
                        self.new_hosts[h["name"]].acknowledged = bool(int(h["acknowledged"]))
                        self.new_hosts[h["name"]].scheduled_downtime = bool(int(h["scheduled_downtime_depth"]))
                        self.new_hosts[h["name"]].status_type = {0: "soft", 1: "hard"}[h["state_type"]]
                    del h
        except:
            import traceback
            traceback.print_exc(file=sys.stdout)
            # set checking flag back to False
            self.isChecking = False
            result, error = self.Error(sys.exc_info())
            return Result(result=result, error=error)

        # services
        try:
            # JSON experiments
            result = self.FetchURL(self.cgiurl_services, giveback="raw")
            jsonraw, error, status_code = copy.deepcopy(result.result),\
                                          copy.deepcopy(result.error),\
                                          result.status_code

            # check if any error occured
            errors_occured = self.check_for_error(jsonraw, error, status_code)
            # if there are errors return them
            if errors_occured != False:
                return(errors_occured)

            # in case basic auth did not work try form login cookie based login
            if jsonraw.startswith("<"):
                self.CookieAuth = True
                return Result(result=None, error="Login failed")

            # in case JSON is not empty evaluate it
            elif not jsonraw == "[]":
                services = json.loads(jsonraw)

                for s in services:
                    # host objects contain service objects
                    if s["host_name"] not in self.new_hosts:
                        self.new_hosts[s["host_name"]] = GenericHost()
                        self.new_hosts[s["host_name"]].name = s["host_name"]
                        self.new_hosts[s["host_name"]].server = self.name
                        self.new_hosts[s["host_name"]].status = "UP"

                    # if a service does not exist create its object
                    if s["description"] not in self.new_hosts[s["host_name"]].services:
                        # ##new_service = s["description"]
                        self.new_hosts[s["host_name"]].services[s["description"]] = GenericService()
                        self.new_hosts[s["host_name"]].services[s["description"]].host = s["host_name"]
                        self.new_hosts[s["host_name"]].services[s["description"]].name = s["description"]
                        self.new_hosts[s["host_name"]].services[s["description"]].server = self.name
                        self.new_hosts[s["host_name"]].services[s["description"]].status = self.STATES_MAPPING["services"][s["state"]]
                        self.new_hosts[s["host_name"]].services[s["description"]].last_check = datetime.datetime.fromtimestamp(int(s["last_check"])).isoformat(" ")
                        self.new_hosts[s["host_name"]].services[s["description"]].duration = HumanReadableDurationFromTimestamp(s["last_state_change"])
                        self.new_hosts[s["host_name"]].services[s["description"]].attempt = "%s/%s" % (s["current_attempt"], s["max_check_attempts"])
                        self.new_hosts[s["host_name"]].services[s["description"]].status_information = s["plugin_output"].replace("\n", " ").strip()
                        self.new_hosts[s["host_name"]].services[s["description"]].passiveonly = not(bool(int(s["active_checks_enabled"])))
                        self.new_hosts[s["host_name"]].services[s["description"]].notifications_disabled = not(bool(int(s["notifications_enabled"])))
                        self.new_hosts[s["host_name"]].services[s["description"]].flapping = not(bool(int(s["notifications_enabled"])))
                        self.new_hosts[s["host_name"]].services[s["description"]].acknowledged = bool(int(s["acknowledged"]))
                        self.new_hosts[s["host_name"]].services[s["description"]].scheduled_downtime = bool(int(s["scheduled_downtime_depth"]))
                        self.new_hosts[s["host_name"]].services[s["description"]].status_type = {0: "soft", 1: "hard"}[s["state_type"]]
                        del s
        except:
            import traceback
            traceback.print_exc(file=sys.stdout)
            # set checking flag back to False
            self.isChecking = False
            result, error = self.Error(sys.exc_info())
            return Result(result=result, error=error)

        # dummy return in case all is OK
        return Result()
