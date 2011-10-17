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
        self.relinker = Relinker(transmogrifier, name, options, self.tidy())
        self.condition = Condition(options.get('condition', 'python:True'),
                                   transmogrifier, name, options)
        self.logger = logging.getLogger(name)
        self.options = options

        self.locale = getattr(options, 'locale', 'en')
        self.link_expr = None
        self.name = name
        self.logger = logging.getLogger(name)
        if options.get('link_expr', None):
            self.link_expr = Expression(
                    options['link_expr'],
                    transmogrifier, name, options)
        self.use_title = Condition(options.get('condition', 'python:False'),
                                   transmogrifier, name, options)
        #util = queryUtility(IURLNormalizer)
        #if util:
        #    self.normalize = util.normalize
        #else:
        self.locale = Expression(options.get('locale', 'python:None'),
                                transmogrifier, name, options)


    def __iter__(self):
        for item in self.relinker:
            yield item

    def tidy(self):

        self.logger.info("condition=%s" % (self.options.get('condition', 'python:True')))
        items = []


        for item in self.previous:

            # find the sitemap

            if not self.condition(item):
                self.logger.debug("skipping %s (condition)" % (path))
                items.append( item )
                continue

            # analyse the site map
            xml = item.get('text','')

            events = ("start", "end")
            context = etree.iterparse(StringIO(xml), events=events)
            for action, elem in context:
                if action == 'start':
                    if elem.tag == 'a':
                        href = elem.tag.href
                        href = make_relative(href)
                        parents = href.split('/')
                    else:
                        invtree[href]
                print("%s: %s" % (action, elem.tag))

        for item in items:
            path = item['_path']
            parents = invtree.get(path,None)
            if parents:
                origin = item.get('_origin')
                if not origin:
                    item['_origin'] = path
                path = '/'.join(parents)
                item['_path'] = path
            yield item



