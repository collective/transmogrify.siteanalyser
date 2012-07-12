
import fnmatch
from zope.interface import classProvides
from zope.interface import implements
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.utils import Matcher,Condition
from urllib import unquote
import urlparse
import re
import logging
from treeserializer import TreeSerializer

"""
Backlinks Title
===============

This blueprint will take the _backlinks from the item generated by webcrawler
and if not Title field has been given to the item it will attempt to guess
it from the link names that linked to this document.
You can specify an option 'ignore' option to specify titles never to use

If it can't guess it from the backlinks it will default to using the file name after
cleaning it up somewhat
"""

class BacklinksTitle(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.toignore=options.get('ignore','next\nprevios\n').strip().split('\n')
        self.toignore_re=options.get('ignore_re','').strip().split('\n')
        self.treeserializer = TreeSerializer(transmogrifier, name, options, previous)
        self.condition = Condition(options.get('condition', 'python:True'),
                                   transmogrifier, name, options)
        self.logger = logging.getLogger(name)
        self.options = options


    def __iter__(self):
        self.logger.debug("condition=%s" % (self.options.get('condition', 'python:True')))
        self.logger.debug("ignore=%s" % (self.toignore))
        items = []
        defaultpages  = {}
        countid = 0
        countbacklinks = 0
        counttotal = 0
        skipped = 0
        countparent = 0
        for item in self.treeserializer:
            path = item.get('_path', None)
            backlinks = item.get('_backlinks',[])
            title = item.get('title')
            defaultpage = item.get('_defaultpage')
            if path is None:
                items.append(item)
                continue

            counttotal += 1
                
            if not self.condition(item):
                items.append( item )
                self.logger.debug("%s skipped (condition)" % (path))
                skipped +=1
                continue  
            elif title:
                items.append( item )
                self.logger.debug('%s existingtitle="%s"' % (path,title))
                continue
            elif defaultpage:
                # save and we'll use that for title
                indexpath = urlparse.urljoin(path+'/', defaultpage)
                defaultpages[indexpath] = item
                items.append( item )
                continue
            names = []
            for url, name in backlinks:
                if not name.strip():
                    continue
                pat = self.ignore(name)
                if pat is not None:
                    self.logger.debug('pat="%s" ignoring title="%s"'%(pat,name))
                else:
                    names.append(name)
            # do a vote
            votes = {}
            for name in names:
                votes[name] = votes.get(name,0) + 1
            votes = [(c,name) for name,c in votes.items()]
            votes.sort()
            title = None
            if votes:
                c,title = votes[-1]
                title = title.strip()
            else:
                if backlinks:
                    self.logger.debug('%s ignored backlinks' % (path))
                else:
                    self.logger.debug('%s no backlinks' % (path))

            if title:
                item['title']=title
                self.logger.debug('%s bl_title="%s" (from backlinks)' % (path,item['title']))
                countbacklinks += 1
            else:
                if self.titlefromid(item):
                    countid += 1
            # go back and title the folder if this is a default page
                
            items.append( item )
        items2 = []
        for item in items:
            path = item.get('_path')
            folder = defaultpages.get(path)
            if folder:
                if 'title' in item:
                    folder['title'] = item['title']
                    countparent += 1
                if 'description' in item:
                    folder['description'] = item['description']
            items2.append( item )
        for item in items2:
            yield item
        self.logger.info("titles=%d/%d (id=%d,backlinks=%d,parent=%d)" %
            (countid+countbacklinks+countparent,
                counttotal,
                countid,
                countbacklinks,
                countparent)
        )

    def ignore(self, name):
        for pat in self.toignore:
            if re.search(pat,name):
                return pat
        for pat in self.toignore_re:
            if re.match(pat,name):
                return pat
        return None

    def titlefromid(self, item):
        path = item.get('_path')
        if not path:
            return False
        title = [p for p in path.split('/') if p][-1]
        title = unquote(title)
        title = title.split('.')[0]
        item['title'] = title
        self.logger.debug('%s id_title="%s" (from id)' % (path,item['title']))
        return True
