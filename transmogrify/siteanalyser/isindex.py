import fnmatch
from StringIO import StringIO
from sys import stderr

import lxml.html
import lxml.html.soupparser
from lxml import etree

from zope.interface import classProvides
from zope.interface import implements
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.utils import Matcher
from collective.transmogrifier.utils import Expression, Condition
from treeserializer import TreeSerializer

import logging


class IsIndex(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.min_links = options.get('min_links', 2)
        self.max_uplinks = options.get('max_uplinks', 2)
        self.mode = options.get('mode', 'links')
        if self.mode == 'path':
            self.parent_path = Expression(options['parent_path'],
                                          transmogrifier, name, options)
            self.treeserializer = TreeSerializer(transmogrifier, name, options,
                                                 previous)
        self.condition = Condition(options.get('condition', 'python:True'),
                                   transmogrifier, name, options)
        self.logger = logging.getLogger(name)
        
            
    def __iter__(self):
        # set common defaults
        self.moved = {}
        
        # generate source items based on selected mode
        if self.mode == 'path':
            source = self.index_by_path
        # default mode is 'links'
        else:
            source = self.index_by_links
        
        # finally yield generated source items
        for item in source():
            yield item
    
    def index_by_path(self):
        """This mode moves item based on it's url. Rule is defined by entered
        parent_path option which is expression with access to item,
        transmogrifier, name, options and modules variables.
        Returned value is used to find possible parent item by path. If found,
        item is moved to that parent item, parent item _defaultpage key is set
        appropriately, and we turn to processing another item in a pipeline. So
        the first item in pipeline will take precedence in case parent_path rule
        returns more than one item for the same parent.
        """
        # collect items mapping to have an easy access to paths
        items = {}
        for item in self.treeserializer:
            path = item.get('_path', None)
            if path is None:
                yield item
                continue
            if not self.condition(item):
                self.logger.debug("skip %s (condition)"% path)
                yield item
                continue
            
            if '_origin' in item:
                self.moved[item['_origin']] = path
            
            items[path] = item
        
        # main job is done in this cycle
        for path, item in items.items():
            parent_path = self.parent_path(item)
            if parent_path == path:
                continue
            
            if parent_path in items:
                parent = items[parent_path]
                
                if parent.get('_defaultpage'):
                    self.logger.debug( u"skip moving %s to %s because "
                                              "container already has "
                                              "_defaultpage assigned to %s" % (
                               path, parent_path, parent.get('_defaultpage')))
                else:
                    # found default page, move it to it's parent and assign
                    # _defaultpage key to that container
                    # make sure item id is unique in a target container
                    i = 1
                    item_id = new_id = path.split('/')[-1]
                    new_path = '%s/%s' % (parent_path, item_id)
                    while new_path in items:
                        new_id = "%s%s" % (item_id, i)
                        new_path = '%s/%s' % (parent_path, item_id)
                        i += 1
                    parent['_defaultpage'] = new_id
                    item['_path'] = new_path
                    item.setdefault('_origin', path)
                    self.moved[path] = item['_path']
                    logger.log(logging.DEBUG, u"moved %s to %s/%s" % (path,
                               parent_path, new_id))
                    del items[path]
                    yield item
            else:
                self.logger.debug( u"can't move %s to %s because "
                                          "container not found" % (
                                          path, parent_path))
        
        for item in items.values():
            yield item
    
    def index_by_links(self):
        """This mode parses item's content html code for links and moves it
        to a folder to which found links point.
        """
        items = {}
        ulinks = {}
        for item in self.previous:
            path, html = self.ishtml(item)
            if not path:
                yield item
                continue            
            elif not self.condition(item):
                self.logger.debug("skip %s (condition)"% path)
                yield item
                continue
            try:
                tree = lxml.html.fromstring(html)
            except:
                tree = lxml.html.fragment_fromstring(html, create_parent=True)

            base = item.get('_site_url', '')
            tree.make_links_absolute(base+path)
            if '_origin' in item:
                self.moved[item['_origin']] = path
            
            # collect all links on a page
            links = []
            items[path] = (item, path, links)
            for element, attribute, link, pos in tree.iterlinks():
                if attribute == 'href' and link not in ulinks:
                    ulinks[link] = True
                    if link.startswith(base):
                        link = link[len(base):]
                    link = '/'.join([p for p in link.split('/') if p])
                    links.append(link)
        
        # move pages into it's containers if needed;
        # we define it here by number of links pointing to this or another
        # folder, wins that page which has more links ponting to a folder
        done = []
        while items:
            indexes = {}
            for item, path, links in items.values():
                if not links:
                    continue
                count, dir, rest = self.indexof(links)
#                print >> stderr, (count, len(links), dir, path,
#                                  item.get('_template'), rest)
                if self.isindex(count, links):
                    indexes.setdefault(dir, []).append((count, item, path,
                                                        links, dir))
            
            # get the deepest folder and move appropriate items into it
            mostdeep = [(len(dir.split('/')), i) for dir, i in indexes.items()]
            if not mostdeep:
                break
            mostdeep.sort()
            depth, winner = mostdeep[-1]
            self.move(winner)
            for count, item, path, links, dir in winner:
                del items[path]
                yield item
        
        # yield any left items, those ones that don't have links to any folders
        for item, path, links in items.values():
            yield item

    def move(self, items):
        if not items:
            return
        items.sort()
        
        # hm, not sure why do we need the next line here?
        count, item, toppath, links, dir = items[-1]
        
        for count, item, path, links, dir in items:
            # TODO: need a better way to work out default view
            if False: #path == toppath:
                file = 'index_html'
            else:
                file = path.split('/')[-1]
            
            if dir:
                target = dir + '/' + file
            else:
                target = file
            
            if item['_path'] == target:
                continue
            
            item.setdefault('_origin', path)
            item['_path'] = target
                
            self.moved[path] = item['_path']
            msg = "moved %s to %s/%s" % (path, dir, file)
            logger.log(logging.DEBUG, msg)

    def isindex(self, count, links):
        return count >= self.min_links and \
               count >= len(links) - self.max_uplinks

    def indexof(self, links):
        dirs = {}
        def most(count):
            return self.isindex(count, links)

        # collect directories based on a page links
        for link in links:
            newlink = self.moved.get(link)
            if newlink:
                link = newlink
            dir = '/'.join([p for p in link.split('/') if p][:-1])
            dirs[dir] = dirs.get(dir, 0) + 1
        
        # page has no links pointing to folders
        if not dirs:
            return 0, None, dirs
        
        alldirs = dirs
        while True:
            tops = [(count, dir) for dir, count in dirs.items()]
            tops.sort()
            count, dir = tops[-1]
            
            # check if we already found top directory our page is referencing to
            if most(count) or len(tops) < 2:
                break
            
            # find common dir; take the longest path and make it shorter
            common = [(dir, count) for count, dir in tops]
            common.sort()
            common.reverse()
            longdir, longcount = common[0]
            longdir = '/'.join(longdir.split('/')[:-1])
            dirs = dict(common[1:])
            dirs[longdir] = dirs.get(longdir, 0) + longcount
            
        return count, dir, alldirs
    
#            tops = []
#            found = False
#            for dir,count in common[1:]:
#                if not found and longdir.startswith(dir) and dir:
#                    count = count+longcount
#                    found = True
#                tops.append((count,dir))


    def ishtml(self, item):
        path = item.get('_path', None)
        content = item.get('_content', None) or item.get('text', None)
        mimetype = item.get('_mimetype', None)
        if  path and content and mimetype in ['text/xhtml', 'text/html']:
            return path, content
        else:
            return None, None
