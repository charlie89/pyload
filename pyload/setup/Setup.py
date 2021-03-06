#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#   Copyright(c) 2008-2013 pyLoad Team
#   http://www.pyload.org
#
#   This file is part of pyLoad.
#   pyLoad is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   Subjected to the terms and conditions in LICENSE
#
#   @author: RaNaN
###############################################################################

import os
import sys
import socket
import gettext
import webbrowser

from getpass import getpass
from time import time
from sys import exit


from pyload.Api import Role
from pyload.utils.fs import abspath, dirname, exists, join, makedirs
from pyload.utils import get_console_encoding
from pyload.web.ServerThread import WebServer

from system import get_system_info
from dependencies import deps

class Setup():
    """
    pyLoads initial setup configuration assistant
    """

    @staticmethod
    def check_system():
        return get_system_info()


    @staticmethod
    def check_deps():
        result = {
            "core": [],
            "opt": []
        }

        for d in deps:
            avail, v = d.check()
            check = {
                "name": d.name,
                "avail": avail,
                "v": v
            }
            if d.optional:
                result["opt"].append(check)
            else:
                result["core"].append(check)

        return result


    def __init__(self, path, config):
        self.path = path
        self.config = config
        self.stdin_encoding = get_console_encoding(sys.stdin.encoding)
        self.lang = None
        self.db = None

        # We will create a timestamp so that the setup will be completed in a specific interval
        self.timestamp = time()

        # TODO: probably unneeded
        self.yes = "yes"
        self.no = "no"

    def start(self):
        import __builtin__
        # set the gettext translation
        __builtin__._ = lambda x: x

        web = WebServer(pysetup=self)
        web.start()

        error = web.check_error()

        # TODO: start cli in this case
        if error: #todo errno 44 port already in use
            print error

        url = "http://%s:%d/" % (socket.gethostbyname(socket.gethostname()), web.port)

        print "Setup is running at %s" % url

        opened = webbrowser.open_new_tab(url)
        if not opened:
            print "Please point your browser to the url above."

        cli = self.ask("Use commandline for configuration instead?", self.no, bool=True)
        if cli:
            print "Not implemented yet!"
            print "Use web configuration or config files"

        raw_input()

        return True


    def start_cli(self):

        self.ask_lang()

        print _("Welcome to the pyLoad Configuration Assistent.")
        print _("It will check your system and make a basic setup in order to run pyLoad.")
        print ""
        print _("The value in brackets [] always is the default value,")
        print _("in case you don't want to change it or you are unsure what to choose, just hit enter.")
        print _(
            "Don't forget: You can always rerun this assistent with --setup or -s parameter, when you start pyLoadCore.")
        print _("If you have any problems with this assistent hit CTRL+C,")
        print _("to abort and don't let him start with pyLoadCore automatically anymore.")
        print ""
        print _("When you are ready for system check, hit enter.")
        raw_input()


        # TODO: new system check + deps

        con = self.ask(_("Continue with setup?"), self.yes, bool=True)

        if not con:
            return False

        print ""
        print _("Do you want to change the config path? Current is %s") % abspath("")
        print _(
            "If you use pyLoad on a server or the home partition lives on an internal flash it may be a good idea to change it.")
        path = self.ask(_("Change config path?"), self.no, bool=True)
        if path:
            self.conf_path()
            #calls exit when changed

        print ""
        print _("Do you want to configure login data and basic settings?")
        print _("This is recommend for first run.")
        con = self.ask(_("Make basic setup?"), self.yes, bool=True)

        if con:
            self.conf_basic()

        if ssl:
            print ""
            print _("Do you want to configure ssl?")
            ssl = self.ask(_("Configure ssl?"), self.no, bool=True)
            if ssl:
                self.conf_ssl()

        print ""
        print _("Do you want to configure webinterface?")
        web = self.ask(_("Configure webinterface?"), self.yes, bool=True)
        if web:
            self.conf_web()

        print ""
        print _("Setup finished successfully.")
        print _("Hit enter to exit and restart pyLoad")
        raw_input()
        return True


    def conf_basic(self):
        print ""
        print _("## Basic Setup ##")

        print ""
        print _("The following logindata is valid for CLI, GUI and webinterface.")

        from pyload.database import DatabaseBackend

        db = DatabaseBackend(None)
        db.setup()
        username = self.ask(_("Username"), "User")
        password = self.ask("", "", password=True)
        db.addUser(username, password)
        db.shutdown()

        print ""
        langs = self.config.getMetaData("general", "language")
        self.config["general"]["language"] = self.ask(_("Language"), "en", langs.type.split(";"))

        self.config["general"]["download_folder"] = self.ask(_("Download folder"), "Downloads")
        self.config["download"]["max_downloads"] = self.ask(_("Max parallel downloads"), "3")

        reconnect = self.ask(_("Use Reconnect?"), self.no, bool=True)
        self.config["reconnect"]["activated"] = reconnect
        if reconnect:
            self.config["reconnect"]["method"] = self.ask(_("Reconnect script location"), "./reconnect.sh")


    def conf_web(self):
        print ""
        print _("## Webinterface Setup ##")

        print ""
        self.config["webinterface"]["activated"] = self.ask(_("Activate webinterface?"), self.yes, bool=True)
        print ""
        print _("Listen address, if you use 127.0.0.1 or localhost, the webinterface will only accessible locally.")
        self.config["webinterface"]["host"] = self.ask(_("Address"), "0.0.0.0")
        self.config["webinterface"]["port"] = self.ask(_("Port"), "8000")
        print ""
        print _("pyLoad offers several server backends, now following a short explanation.")
        print "threaded:", _("Default server, this server offers SSL and is a good alternative to builtin.")
        print "fastcgi:", _(
            "Can be used by apache, lighttpd, requires you to configure them, which is not too easy job.")
        print "lightweight:", _("Very fast alternative written in C, requires libev and linux knowledge.")
        print "\t", _("Get it from here: https://github.com/jonashaag/bjoern, compile it")
        print "\t", _("and copy bjoern.so to pyload/lib")

        print
        print _(
            "Attention: In some rare cases the builtin server is not working, if you notice problems with the webinterface")
        print _("come back here and change the builtin server to the threaded one here.")

        self.config["webinterface"]["server"] = self.ask(_("Server"), "threaded",
            ["builtin", "threaded", "fastcgi", "lightweight"])

    def conf_ssl(self):
        print ""
        print _("## SSL Setup ##")
        print ""
        print _("Execute these commands from pyLoad config folder to make ssl certificates:")
        print ""
        print "openssl genrsa -out ssl.key 1024"
        print "openssl req -new -key ssl.key -out ssl.csr"
        print "openssl req -days 36500 -x509 -key ssl.key -in ssl.csr > ssl.crt "
        print ""
        print _("If you're done and everything went fine, you can activate ssl now.")
        self.config["ssl"]["activated"] = self.ask(_("Activate SSL?"), self.yes, bool=True)

    def set_user(self):
        translation = gettext.translation("setup", join(self.path, "locale"),
            languages=[self.config["general"]["language"], "en"], fallback=True)
        translation.install(True)

        self.openDB()

        try:
            while True:
                print _("Select action")
                print _("1 - Create/Edit user")
                print _("2 - List users")
                print _("3 - Remove user")
                print _("4 - Quit")
                action = raw_input("[1]/2/3/4: ")
                if not action in ("1", "2", "3", "4"):
                    continue
                elif action == "1":
                    print ""
                    username = self.ask(_("Username"), "User")
                    password = self.ask("", "", password=True)
                    admin = self.ask("Admin?", self.yes, bool=True)

                    self.db.addUser(username, password, Role.Admin if admin else Role.User, int('1111111', 2))
                elif action == "2":
                    print ""
                    print _("Users")
                    print "-----"
                    users = self.db.getAllUserData()
                    for user in users.itervalues():
                        print user.name
                    print "-----"
                    print ""
                elif action == "3":
                    print ""
                    username = self.ask(_("Username"), "")
                    if username:
                        self.db.removeUserByName(username)
                elif action == "4":
                    self.db.syncSave()
                    break
        finally:
            self.closeDB()

    def addUser(self, username, password, role=Role.Admin):
        self.openDB()
        try:
            self.db.addUser(username, password, role, int('1111111', 2))
        finally:
            self.closeDB()

    def openDB(self):
        from pyload.database import DatabaseBackend

        if self.db is None:
            self.db = DatabaseBackend(None)
            self.db.setup()

    def closeDB(self):
        if self.db is not None:
            self.db.syncSave()
            self.db.shutdown()

    def save(self):
        self.config.save()
        self.closeDB()

    def conf_path(self, trans=False):
        if trans:
            translation = gettext.translation("setup", join(self.path, "locale"),
                languages=[self.config["general"]["language"], "en"], fallback=True)
            translation.install(True)

        print _("Setting new configpath, current configuration will not be transferred!")
        path = self.ask(_("Config path"), abspath(""))
        try:
            path = join(pypath, path)
            if not exists(path):
                makedirs(path)
            f = open(join(pypath, "pyload", "config", "configdir"), "wb")
            f.write(path)
            f.close()
            print _("Config path changed, setup will now close, please restart to go on.")
            print _("Press Enter to exit.")
            raw_input()
            exit()
        except Exception, e:
            print _("Setting config path failed: %s") % str(e)


    def ask_lang(self):
        langs = self.config.getMetaData("general", "language").type.split(";")
        self.lang = self.ask(u"Choose your Language / Wähle deine Sprache", "en", langs)
        translation = gettext.translation("setup", join(self.path, "locale"), languages=[self.lang, "en"], fallback=True)
        translation.install(True)

        #l10n Input shorthand for yes
        self.yes = _("y")
        #l10n Input shorthand for no
        self.no = _("n")

    def ask(self, qst, default, answers=[], bool=False, password=False):
        """ Generate dialog on command line """

        if answers:
            info = "("
            for i, answer in enumerate(answers):
                info += (", " if i != 0 else "") + str((answer == default and "[%s]" % answer) or answer)

            info += ")"
        elif bool:
            if default == self.yes:
                info = "([%s]/%s)" % (self.yes, self.no)
            else:
                info = "(%s/[%s])" % (self.yes, self.no)
        else:
            info = "[%s]" % default

        if password:
            p1 = True
            p2 = False
            while p1 != p2:
                # getpass(_("Password: ")) will crash on systems with broken locales (Win, NAS)
                sys.stdout.write(_("Password: "))
                p1 = getpass("")

                if len(p1) < 4:
                    print _("Password too short. Use at least 4 symbols.")
                    continue

                sys.stdout.write(_("Password (again): "))
                p2 = getpass("")

                if p1 == p2:
                    return p1
                else:
                    print _("Passwords did not match.")

        while True:
            input = raw_input(qst + " %s: " % info)
            input = input.decode(self.stdin_encoding)

            if input.strip() == "":
                input = default

            if bool:
                #l10n yes, true,t are inputs for booleans with value true
                if input.lower().strip() in [self.yes, _("yes"), _("true"), _("t"), "yes"]:
                    return True
                #l10n no, false,f are inputs for booleans with value false
                elif input.lower().strip() in [self.no, _("no"), _("false"), _("f"), "no"]:
                    return False
                else:
                    print _("Invalid Input")
                    continue

            if not answers:
                return input

            else:
                if input in answers:
                    return input
                else:
                    print _("Invalid Input")


if __name__ == "__main__":
    test = Setup(join(abspath(dirname(__file__)), ".."), None)
    test.start()
