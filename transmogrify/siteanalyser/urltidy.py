
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

#INVALID_IDS = ['security', 'sharing']


"""
transmogrify.siteanalyser.urltidy
=================================
Will  normalize ids in urls to be suitable for adding to plone.

The following will tidy up the URLs based on a TALES expression ::

 $> bin/funnelweb --urltidy:link_expr="python:item['_path'].endswith('.html') and item['_path'][:-5] or item['_path']"

If you'd like to move content around before it's uploaded you can use the urltidy step as well e.g. ::

 $> bin/funnelweb --urltidy:link_expr=python:item['_path'].startswith('/news') and '/otn/news'+item['path'][5:] or item['_path']


Options:

:condition:
  TAL Expression to apply transform

:locale:
  TAL Expression to return the locale used for id normalisation. e.g. 'string:en'

:link_expr:
  TAL Expression to alter the items '_path'

:use_title:
  Condition TAL Expression to change the end path element to a normalised version of item['_title']




"""

class UrlTidy(object):
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
        self.invalid_ids = options.get('invalid_ids', '').split()

        self.link_expr = None
        self.name = name
        self.logger = logging.getLogger(name)
        if options.get('link_expr', None):
            self.link_expr = Expression(
                    options['link_expr'],
                    transmogrifier, name, options)
        self.use_title = Condition(options.get('use_title', 'python:False'),
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

        # keep track of new_path -> _origin to make new ids unique
        seen = {}

        titles = 0
        total = 0
        normed = 0
        skipped = 0

    
        for item in self.previous:
            total += 1

            path = item.get('_path',None)
            if path is None:
                url = item.get('_bad_url')
                yield item
                continue
            if not self.condition(item):
                self.logger.debug("skipping %s (condition)" % (path))
                yield item
                skipped += 1
                continue

            base = item.get('_site_url','')

            origin = item.get('_origin')
            if not origin:
                origin = item['_origin'] = path

            # apply link_expr
            if self.link_expr:
                newpath = self.link_expr(item)
            else:
                newpath = path


            if 'title' in item and self.use_title(item):
                #TODO This has problem that for relinking to work we need to change the full url
                parts = newpath.split('/')
                title = item['title'].strip()
                newpath = '/'.join(parts[:-1] + [self.norm(title, item)])
                id = parts[-1]
                if "." in id:
                    if "?" in id:
                        id,_ = id.split("?",1)
                    id, ext = id.rsplit(".",1)
                    newpath = "%s.%s" %(newpath, ext)
                titles += 1

            #normalize link
            newpath = '/'.join([self.norm(part, item) for part in newpath.split('/')])

            i = 1
            upath = newpath
            while True:
                if upath not in seen:
                    break
                if "." in newpath:
                    start, ext = newpath.rsplit(".",1)
                    upath = "%s-%s.%s" % (start,i,ext)
                else:
                    upath = "%s-%s" % (newpath,i)
                i += 1
            newpath = upath
            seen[newpath] = path


            if newpath != path:
                normed += 1
                self.logger.debug("Normalised path to '%s' from '%s'" % (newpath, path))
            item['_path'] = newpath
            #assert not changes.get(link,None), str((item,changes.get(base+origin,None)))

            yield item

        self.logger.info('titles=%d, normed=%d, total=%d'%(titles,normed,total))



    def norm(self, part, item):
        #TODO - don't normalize to existing names
        if part.startswith('_'):
            part = part[1:]+'-1'
        # Get the information we require for normalization
        keywords = dict(text=urllib.unquote_plus(part), locale=self.locale(item))
        # Perform Normalization
        part = normalizer.normalize(**keywords)
        if part in self.invalid_ids:
            return part + '-1'
        else:
            return part
