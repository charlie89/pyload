# -*- coding: utf-8 -*-

from pyload.Api import LinkStatus, DownloadStatus as DS
from pyload.utils import to_list, has_method, uniqify
from pyload.utils.fs import exists, remove, fs_encode
from Base import Base, Retry


# represent strings as LinkStatus
def to_link_list(links, status=DS.Queued):
    return [LinkStatus(link, link, -1, status) if isinstance(link, basestring) else link
            for link in links]


class Package:
    """ Container that indicates that a new package should be created """

    def __init__(self, name=None, links=None):
        self.name = name

        # list of link status
        self.links = []

        if links:
            self.addLinks(links)

        # nested packages
        self.packs = []

    def addLinks(self, links):
        """ Add one or multiple links to the package

        :param links: One or list of urls or :class:`LinkStatus`
        """
        self.links.extend(to_link_list(to_list(links)))

    def addPackage(self, pack):
        self.packs.append(pack)

    def getURLs(self):
        return [link.url for link in self.links]

    def getAllURLs(self):
        urls = self.getURLs()
        for p in self.packs:
            urls.extend(p.getAllURLs())
        return urls

    # same name and urls is enough to be equal for packages
    def __eq__(self, other):
        return self.name == other.name and self.links == other.links

    def __repr__(self):
        return u"<CrypterPackage name=%s, links=[%s], packs=%s>" % (self.name, ", ".join(str(l) for l in self.links),
                                                                    self.packs)

    def __hash__(self):
        return hash(self.name) ^ hash(frozenset(self.links)) ^ hash(self.name)


class PyFileMockup:
    """ Legacy class needed by old crypter plugins """

    def __init__(self, url, pack_name):
        self.url = url
        self.name = url
        self.packageid = -1
        self.pack_name = pack_name + " Package"

    def package(self):
        # mockes the pyfile package
        class PyPackage:
            def __init__(self, f):
                self.name = f.pack_name
                self.folder = self.name

        return PyPackage(self)


class Crypter(Base):
    """
    Base class for (de)crypter plugins. Overwrite decrypt* methods.

    How to use decrypt* methods:

    You have to overwrite at least one method of decryptURL, decryptURLs, decryptFile.

    After decrypting and generating urls/packages you have to return the result.
    Valid return Data is:

    :class:`Package` instance Crypter.Package
        A **new** package will be created with the name and the urls of the object.

    List of urls and `Package` instances
        All urls in the list will be added to the **current** package. For each `Package`\
        instance a new package will be created.

    """

    #: Prefix to annotate that the submited string for decrypting is indeed file content
    CONTENT_PREFIX = "filecontent:"

    #: Optional name of an account plugin that should be used, but does not guarantee that one is available
    USE_ACCOUNT = None

    #: When True this crypter will not be decrypted directly and queued one by one.
    # Needed for crypter that can't run in parallel or need to wait between decryption.
    QUEUE_DECRYPT = False

    @classmethod
    def decrypt(cls, core, url_or_urls, password=None):
        """Static method to decrypt urls or content. Can be used by other plugins.
        To decrypt file content prefix the string with ``CONTENT_PREFIX `` as seen above.

        :param core: pyLoad `Core`, needed in decrypt context
        :param url_or_urls: List of urls or single url/ file content
        :param password: optional password used for decrypting

        :raises Exception: No decryption errors are cascaded
        :return: List of decrypted urls, all package info removed
        """
        urls = to_list(url_or_urls)
        p = cls(core, password)
        try:
            result = p._decrypt(urls)
        finally:
            p.clean()

        ret = []

        for url_or_pack in result:
            if isinstance(url_or_pack, Package): #package
                ret.extend(url_or_pack.getAllURLs())
            elif isinstance(url_or_pack, LinkStatus): #link
                ret.append(url_or_pack.url)
            else:
                core.log.debug("Invalid decrypter result: " + url_or_pack)

        return uniqify(ret)


    __type__ = "crypter"
    # TODO: pass user to crypter
    def __init__(self, core, password=None):
        Base.__init__(self, core)

        self.req = None
        # load account if set
        if self.USE_ACCOUNT:
            self.account = self.core.accountManager.selectAccount(self.USE_ACCOUNT, self.owner)
            if self.account:
                self.req = self.account.getAccountRequest()

        if self.req is None:
            self.req = core.requestFactory.getRequest()

        #: Password supplied by user
        self.password = password

        # TODO: removed in future
        # For old style decrypter, do not use these!
        self.packages = []
        self.urls = []
        self.pyfile = None

        self.init()

    def init(self):
        """More init stuff if needed"""

    def setup(self):
        """Called everytime before decrypting. A Crypter plugin will be most likely used for several jobs."""

    def decryptURL(self, url):
        """Decrypt a single url

        :param url: url to decrypt
        :return: See :class:`Crypter` Documentation
        """
        if url.startswith("http"): # basic method to redirect
            return self.decryptFile(self.load(url))
        else:
            self.fail(_("Not existing file or unsupported protocol"))

    def decryptURLs(self, urls):
        """Decrypt a bunch of urls

        :param urls: list of urls
        :return: See :class:`Crypter` Documentation
        """
        raise NotImplementedError

    def decryptFile(self, content):
        """Decrypt file content

        :param content: content to decrypt as string
        :return: See :class:`Crypter` Documentation
        """
        raise NotImplementedError

    def _decrypt(self, urls):
        """Internal method to select decrypting method

        :param urls: List of urls/content
        :return: (links, packages)
        """
        cls = self.__class__

        # separate local and remote files
        content, urls = self.getLocalContent(urls)
        result = []

        if urls and has_method(cls, "decrypt"):
            self.logDebug("Deprecated .decrypt() method in Crypter plugin")
            result = []
            for url in urls:
                self.pyfile = PyFileMockup(url, cls.__name__)
                self.setup()
                self.decrypt(self.pyfile)
                result.extend(self.convertPackages())
        elif urls:
            method = True
            try:
                self.setup()
                result = to_list(self.decryptURLs(urls))
            except NotImplementedError:
                method = False

            # this will raise error if not implemented
            if not method:
                for url in urls:
                    self.setup()
                    result.extend(to_list(self.decryptURL(url)))

        for f, c in content:
            self.setup()
            result.extend(to_list(self.decryptFile(c)))
            try:
                if f.startswith("tmp_"): remove(f)
            except IOError:
                self.logWarning(_("Could not remove file '%s'") % f)
                self.core.print_exc()

        return to_link_list(result)

    def getLocalContent(self, urls):
        """Load files from disk and separate to file content and url list

        :param urls:
        :return: list of (filename, content), remote urls
        """
        content = []
        # do nothing if no decryptFile method
        if hasattr(self.__class__, "decryptFile"):
            remote = []
            for url in urls:
                path = None
                if url.startswith("http"): # skip urls directly
                    pass
                elif url.startswith(self.CONTENT_PREFIX):
                    path = url
                elif exists(url):
                    path = url
                elif exists(self.core.path(url)):
                    path = self.core.path(url)

                if path:
                    try:
                        if path.startswith(self.CONTENT_PREFIX):
                            content.append(("", path[len(self.CONTENT_PREFIX)]))
                        else:
                            f = open(fs_encode(path), "rb")
                            content.append((f.name, f.read()))
                            f.close()
                    except IOError, e:
                        self.logError("IOError", e)
                else:
                    remote.append(url)

            #swap filtered url list
            urls = remote

        return content, urls

    def retry(self):
        """ Retry decrypting, will only work once. Somewhat deprecated method, should be avoided. """
        raise Retry()

    def getPassword(self):
        """ Deprecated """
        self.logDebug("Deprecated method .getPassword(), use self.password instead.")
        return self.password

    def convertPackages(self):
        """ Deprecated """
        self.logDebug("Deprecated method .convertPackages()")
        res = []
        for pack in self.packages:
            # only use name and urls
            res.append(Package(pack[0], pack[1]))

        res.extend(self.urls)
        return res

    def clean(self):
        if hasattr(self, "req"):
            self.req.close()
            del self.req
