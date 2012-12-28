from zope.interface import implements
from zope.interface import classProvides
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection
import urllib
from lxml import etree
import lxml
from urlparse import urljoin
from external.relative_url import relative_url
from collective.transmogrifier.utils import Expression
import logging
import urlparse
import re


"""
transmogrify.siteanalyser.relinker
==================================
Help restructure your content.
If you'd like to move content from one path to another then in a
previous blueprints adjust the '_path' to the new path. Create a new field
called '_origin' and put the old path into that. Once you pass it through
the relinker all href, img tags etc will be changed in any html content where they
pointed to content that has since moved. All '_origin' fields will be removed
after relinking.

Options:

:ignore_duplicates:
  If 'True' there won't be an error raised when two items were redirected from the same place. This can occur with
  some CMS's where content can be in different urls in the site
=======
#import urllib
from external.relative_url import relative_url
#from sys import stderr
#from collective.transmogrifier.utils import Expression
import logging
#from external.normalize import urlnormalizer as normalizer
import urlparse
#from sys import stderr
#from plone.i18n.normalizer import urlnormalizer as normalizer
>>>>>>> 99c848b08ab582b860086322b5419436c7163d49

:broken_link_normalise:
  TAL expressions, each on a new line, which take 'url' from inside the html and returns a link that will match one of
  the existing links in the site. Must return the full url, not the path. This is useful when many different links
  could go to the same content.

"""

class Counter:
    counter = 0


class Relinker(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.name = name
        self.logger = logging.getLogger(name)
        self.ignore_duplicates = options.get('ignore_duplicates', 'False').lower() in ['true', 'on']
        self.broken_link_normalise = []
        for f in options.get('broken_link_normalise','').split('\n'):
            f = f.strip()
            if not f:
                continue
            expr = Expression(f, transmogrifier, name, options, re=re, urlparse=urlparse)
            self.broken_link_normalise.append(expr)

    def __iter__(self):
        #TODO need to fix relative links

        changes = {}
        bad = {}
        items = {}

        self.missing = set([])
        self.bad_pages = 0

        for item in self.previous:
            path = item.get('_path', None)
            if path is None:
                url = item.get('_bad_url')
                if url:
                    bad[url] = item
                yield item
                continue
            base = item.get('_site_url', '')

            origin = item.get('_origin')
            if not origin:
                origin = item['_origin'] = path
            else:
                self.logger.debug("%s <- %s (relinked)" % (path, origin))
            link = urllib.unquote_plus(base + origin)

            if link in changes:
                self.logger.warning("duplicate redirects: both '%s 'and '%s' were redirected from '%s'" %
                    (changes[link]['_path'], item['_path'], link))
                # it happens when both links, which have different text, eg: street and road, link to same URL
                # should we raise exception?

            if link in changes and not self.ignore_duplicates:
                raise Exception("duplicate redirects: both '%s 'and '%s' were redirected from '%s'" %
                            (changes[link]['_path'], item['_path'], link))

            changes[link] = item
            items[path] = item

        for item in changes.values():
            counter = Counter()

            if '_defaultpage' in item:
                # get index item based on it's old path

                if '_origin' in item:
                    oldpath = item['_origin']
                else:
                    # maybe we didn't change but the index did
                    oldpath = item['_path']
                indexpath = item['_site_url'] + '/'.join([p for p in [oldpath, item['_defaultpage']] if p])
                newindex = changes.get(indexpath)
                #need to work out if the new index is still in this folder
                if newindex is not None:
                    # is the parent of our indexpage still 'item'?
                    indexparentpath = '/'.join(newindex['_path'].split('/')[:-1])
                    indexparent = items.get(indexparentpath)
                    if indexparent == item:
                        newindexid = newindex['_path'].split('/')[-1]
                        item['_defaultpage'] = newindexid
                        self.logger.debug("'%s' default page stay" % (item['_path']))
                    else:
                        #import pdb; pdb.set_trace()
                        self.logger.warning("'%s' default page '%s' was moved out of this folder (%s)" %
                                            (item['_path'], item['_defaultpage'], newindex['_path']))
                        del item['_defaultpage']
                        # leave in defaultpage and hope redirection takes care of it
                    #    import pdb; pdb.set_trace()
                else:
                    indexpath = item['_path'] + '/' + item['_defaultpage']
                    if indexpath in items:
                        # we don't need to rewrite defaultpage
                        pass
                    else:
                        # why was it set then?? #TODO
                        # index moved elsewhere so defaultpage setting is off
                        #import pdb; pdb.set_trace()
                        self.logger.warning("'%s' had default page '%s' set but it is missing. Removing defaultpage reference" % (item['_path'], item['_defaultpage']))
                        del item['_defaultpage']
            if 'remoteUrl' in item:
                link = item['_site_url'] + urljoin(item['_origin'], item['remoteUrl'])
                # have to put ./ in front of Link
                item['remoteUrl'] = "./" + replace(link, item, changes, counter, self.missing, bad)

            self.relinkHTML(item, changes, counter, bad)

            del item['_origin']
            #rewrite the backlinks too
            backlinks = item.get('_backlinks', [])
            newbacklinks = []
            for origin, name in backlinks:
                #assume absolute urls
                backlinked = changes.get(origin)
                if backlinked:
                    backlink = backlinked['_site_url'] + backlinked['_path']
                    newbacklinks.append((backlink, name))
                else:
                    newbacklinks.append((origin, name))
            if backlinks:
                item['_backlinks'] = newbacklinks

            yield item
        if self.missing:
            self.logger.warning("%d broken internal links in %d pages. "
                                "Content maybe missing. Debug to see details." % (len(self.missing), self.bad_pages))

    def relinkHTML(self, item, changes, counter, bad={}):
        oldbase = item['_site_url'] + item['_origin']
        # guess which fields are html by trying to parse them
        html = {}
        for key, value in item.items():
            if value is None or getattr(value, 'find', None) is None:
                continue
            elif '<' not in value:
                continue
            try:
                html[key] = lxml.html.fromstring(value)
            except lxml.etree.ParseError:
                try:
                    html[key] = lxml.html.fragment_fromstring(value, create_parent=True)
                except lxml.etree.ParseError:
                    pass

        missing = set([])
        item_replace = lambda link: replace(link, item, changes, counter, missing, bad, self.broken_link_normalise)
        self.missing = self.missing.union(missing)
        if missing:
            self.bad_pages += 1

        for field, tree in html.items():
            old_count = counter.counter

            try:
                tree.rewrite_links(item_replace, base_href=oldbase)
            except:
                self.logger.error("Error rewriting links in %s" % item['_origin'])
                raise
            # only update fields which had links in
            if counter.counter != old_count:
                item[field] = etree.tostring(tree, pretty_print=True, encoding=unicode, method='html')
        for link in missing:
            self.logger.debug("%s broken link '%s'" % (item['_path'], link))
        self.logger.debug("'%s' relinked %s links in %s" % (item['_path'], counter.counter, html.keys()))

     #   except Exception:
     #       msg = "ERROR: relinker parse error %s, %s" % (path,str(Exception))
     #       logger.log(logging.ERROR, msg, exc_info=True)


def swapfragment(link, newfragment):
    t = urlparse.urlparse(link)
    fragment = t[-1]
    t = t[:-1] + (newfragment,)
    link = urlparse.urlunparse(t)
    return link, fragment

def removeprotocol(url):
    t = urlparse.urlparse(url)
    return urlparse.urlunparse(['']+list(t[1:]))

def replace(link, item, changes, counter, missing, bad, normalisers):
    path = item['_path']
    newbase = item['_site_url'] + path

    link, fragment = swapfragment(link, '')

    linked = changes.get(link)
    if not linked:
        linked = changes.get(urllib.unquote_plus(link))
    if not linked:
        for norm in normalisers:
            linked = changes.get( norm(item, url=link) )
            if linked:
                break


    if linked:
        linkedurl = item['_site_url'] + linked['_path']
        newlink = swapfragment(relative_url(newbase, linkedurl), fragment)[0]
        counter.counter += 1
    else:
        if link not in bad and link.startswith(item['_site_url']):
            missing.add(link)
        newlink = swapfragment(relative_url(newbase, link), fragment)[0]
    # need to strip out null chars as lxml spits the dummy
    newlink = ''.join([c for c in newlink if ord(c) > 32])
#            self.logger.debug("'%s' -> '%s'" %(link,newlink))
    return newlink
