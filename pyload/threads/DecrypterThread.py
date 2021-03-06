#!/usr/bin/env python
# -*- coding: utf-8 -*-

from time import sleep

from pyload.Api import LinkStatus, DownloadStatus as DS, ProgressInfo, ProgressType
from pyload.utils import uniqify, accumulate
from pyload.plugins.Base import Abort, Retry, Fail
from pyload.plugins.Crypter import Package

from BaseThread import BaseThread


class DecrypterThread(BaseThread):
    """thread for decrypting"""

    def __init__(self, manager, data, fid, pid, owner):
        BaseThread.__init__(self, manager, owner)
        # [... (url, plugin) ...]
        self.data = data
        self.fid = fid
        self.pid = pid
        # holds the progress, while running
        self.progress = None
        # holds if an error happened
        self.error = False

        self.start()

    def getProgress(self):
        return self.progress

    def run(self):
        pack = self.core.files.getPackage(self.pid)
        api = self.core.api.withUserContext(self.owner)
        links, packages = self.decrypt(accumulate(self.data), pack.password)

        # if there is only one package links will be added to current one
        if len(packages) == 1:
            # TODO: also rename the package (optionally)
            links.extend(packages[0].links)
            del packages[0]

        if links:
            self.log.info(
                _("Decrypted %(count)d links into package %(name)s") % {"count": len(links), "name": pack.name})
            api.addLinks(self.pid, [l.url for l in links])

        for p in packages:
            api.addPackage(p.name, p.getURLs(), pack.password)

        self.core.files.setDownloadStatus(self.fid, DS.Finished if not self.error else DS.Failed)
        self.m.done(self)

    def decrypt(self, plugin_map, password=None, err=False):
        result = []

        self.progress = ProgressInfo("BasePlugin", "",  _("decrypting"),
                                         0, 0, len(self.data), self.owner, ProgressType.Decrypting)
        # TODO QUEUE_DECRYPT
        for name, urls in plugin_map.iteritems():
            klass = self.core.pluginManager.loadClass("crypter", name)
            plugin = None
            plugin_result = []

            # updating progress
            self.progress.plugin = name
            self.progress.name = _("Decrypting %s links") % len(urls) if len(urls) > 1 else urls[0]

            #TODO: dependency check, there is a new error code for this
            # TODO: decrypting with result yielding
            if not klass:
                self.error = True
                if err:
                    plugin_result.extend(LinkStatus(url, url, -1, DS.NotPossible, name) for url in urls)
                self.log.debug("Plugin '%s' for decrypting was not loaded" % name)
            else:
                try:
                    plugin = klass(self.core, password)

                    try:
                        plugin_result = plugin._decrypt(urls)
                    except Retry:
                        sleep(1)
                        plugin_result = plugin._decrypt(urls)

                    plugin.logDebug("Decrypted", plugin_result)

                except Abort:
                    plugin.logInfo(_("Decrypting aborted"))
                except Exception, e:
                    plugin.logError(_("Decrypting failed"), e)

                    self.error = True
                    # generate error linkStatus
                    if err:
                        plugin_result.extend(LinkStatus(url, url, -1, DS.Failed, name) for url in urls)

                    # no debug for intentional errors
                    if self.core.debug and not isinstance(e, Fail):
                        self.core.print_exc()
                        self.writeDebugReport(plugin.__name__, plugin=plugin)
                finally:
                    if plugin:
                        plugin.clean()

            self.progress.done += len(urls)
            result.extend(plugin_result)

        # clear the progress
        self.progress = None

        # generated packages
        packs = {}
        # urls without package
        urls = []

        # merge urls and packages
        for p in result:
            if isinstance(p, Package):
                if p.name in packs:
                    packs[p.name].urls.extend(p.urls)
                else:
                    if not p.name:
                        urls.extend(p.links)
                    else:
                        packs[p.name] = p
            else:
                urls.append(p)

        urls = uniqify(urls)

        return urls, packs.values()