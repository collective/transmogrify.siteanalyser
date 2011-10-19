__author__ = 'dylanjay'


from zope.interface import classProvides
from zope.interface import implements
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.utils import Matcher,Condition,Expression
from urllib import unquote
import urlparse
import re
import logging
from relinker import Relinker
from external.normalize import urlnormalizer as normalizer
import urllib
from lxml import etree
from lxml.html import fragment_fromstring
from StringIO import StringIO
from urlparse import urljoin

INVALID_IDS = ['security']


"""
SiteMapper
==========

Analyse html for links in sitemap like structure. Then rearrage items based on that
structure.

"""

class SiteMapper(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.relinker = Relinker(transmogrifier, "relinker", options, self.ouriter())
        self.condition = Condition(options.get('condition', 'python:True'),
                                   transmogrifier, name, options)
        self.logger = logging.getLogger(name)
        self.options = options

        self.name = name
        self.logger = logging.getLogger(name)


    def __iter__(self):
        for item in self.relinker:
            yield item

    def ouriter(self):

        self.logger.info("condition=%s" % (self.options.get('condition', 'python:True')))
        items = []
        newpaths = {}

        for item in self.previous:

            # find the sitemap

            if not self.condition(item):
                items.append( item )
                continue
            path = item.get('_path')
            if not path:
                items.append( item )
                continue

            self.logger.debug("picked sitemap=%s (condition)" % (path))
            # analyse the site map
            html = item.get('text','')
            base = item['_site_url']
            newpaths = self.analyse_sitemap(base, html)
            items.append( item )

        for item in items:
            path = item.get('_path')
            if path in newpaths:
                origin = item.get('_origin')
                if not origin:
                    item['_origin'] = path
                item['_path'] = newpaths[path]
            yield item


    def analyse_sitemap(self, base, html):
        newpaths = {}
        node = fragment_fromstring(html, create_parent=True)
        parents = []
        events = ("start", "end")
        context = etree.iterwalk(node, events=events)
        for action, elem in context:
            if action == 'start':
                if elem.tag == 'a':
                    href = elem.attrib.get('href')
                    if not href:
                        continue
                    href = urljoin(base,href,allow_fragments=False)
                    if not href.startswith(base):
                        continue
                    path = href[len(base):]
                    id = path.split('/')[-1]
                    parents.append(id)
                    # copy parents with extra Nones in
                    newpaths[path] = '/'.join([p for p in parents if p is not None])
                else:
                    parents.append(None)
            elif action == 'end':
                if elem.tag == 'a':
                    pass
                else:
                    parents.pop()
        self.logger.debug("analysed sitemap=\n%s"% str(newpaths))
        return newpaths

