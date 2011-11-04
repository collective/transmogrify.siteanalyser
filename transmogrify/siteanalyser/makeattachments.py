
from zope.interface import classProvides
from zope.interface import implements
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.utils import Condition, Expression
import logging
import lxml
import urlparse



class MakeAttachments(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.fields=Expression(options.get('fields','python:False'), transmogrifier, name, options)
        self.condition=Condition(options.get('condition','python:True'), transmogrifier, name, options)
        self.defaultpage = options.get('defaultpage','index-html')
        self.logger = logging.getLogger(name)

    def __iter__(self):


        previtems = []
        backlinksfor = {}
        for item in self.previous:
            backlinksfor.update(self.getBacklinks(item))
            previtems.append(item)
        else:
            for item in self.previous:
                previtems.append(item)


        # split items on subitems and other
        paths = {}
        items, subitems = [], {}
        for item in previtems:
            backlinks = item.get('_backlinks',[])
            base = item.get('_site_url','')
            path = item.get('_path','')
            origin = item.get('_orig_path','')
            #if not backlinks:
            backlinks = backlinksfor.get(base+path,[])
            if len(backlinks):
                self.logger.debug("%s backlinks=%s backlinks" %
                                  (path, str(backlinks)))
            if len(backlinks) == 1 and origin == path:
                link,name = backlinks[0]
                subitems.setdefault(link, [])
                subitems[link].append(item)
            items.append(item)
            # Store paths to see if we don't overwrite
            if path:
                paths[path] = item
 
        # apply new fields from subitems to items 
        total = 0
        moved = 0
        for item in items:
            base = item.get('_site_url',None)
            origin = item.get('_origin',item.get('_path',None))
            if not base or not origin:
                yield item
                continue
            if not self.condition(item):
                    self.logger.debug("skipping %s (condition)" %(item['_path']))
                    yield item
                    continue
            links = subitems.get(base+origin,[])
            backlinks =  item.get('_backlinks',[])
            if not links and len(backlinks)==1 and subitems.get(backlinks[0][0]) is not None:
                continue #item is a deadend and will be delt with elsewhere
            folder=None
            i = 0
            attach = []
            for subitem in links:
                subbase = subitem.get('_site_url',None)
                suborigin = subitem.get('_origin',subitem.get('_path',None))
                    
                if subitems.get(subbase+suborigin,[]):
                    # subitem isn;t a deadend and will be dealt with elsewhere. 
                    continue
                change = self.fields(item, subitem=subitem, i=i)
                if change:
                    # if we transform element
                    item.update(dict(change))
                    self.logger.debug("%s to %s{%s}" %(suborigin,origin,dict(change).keys()))
                    # now pass a move request to relinker
                    file,text=change[0]
                    attach.append(dict(_origin=suborigin,
                               _path=file,
                               _site_url=subbase))
                else: #turn into default folder
                    if not folder:
                        folder = dict(_path=item['_path'],
                                      _site_url=base,
                                      _type="Folder",
                                      _defaultpage=self.defaultpage)
                        if not item.get('_origin'):
                            item['_origin']=item['_path']
                        newpath = '/'.join(item['_path'].split('/') + [self.defaultpage])
                        newpathi = newpath
                        i = 1
                        while newpathi in paths:
                            newpathi = "%s-%d" % (newpath,i)
                            i = i + 1
                        item['_path'] = newpath
                        paths[newpath] = item
                    else:
                        # need to ensure we don't overwrite whats already there
                        pass
                    if '_origin' not in subitem:
                        subitem['_origin'] = subitem['_path']
                    file = subitem['_path'].split('/')[-1]
                    newpath = '/'.join(folder['_path'].split('/') + [file])
                    newpathi = newpath
                    i = 1
                    while newpathi in paths:
                        newpathi = "%s-%d" % (newpath,i)
                        i = i + 1
                    subitem['_path'] = newpath
                    paths[newpath] = item
                    self.logger.debug("%s <- %s" %
                                      (subitem['_path'],subitem['_origin']))

                    yield subitem
                moved += 1
                i = i +1
            if folder:
                self.logger.debug("%s new folder = %s" %
                                  (item['_path'],folder['_path']))
                yield folder
            yield item
            # got to set actual final paths of attachments moves
            for subitem in attach:
                subitem['_path'] = '/'.join(item['_path'].split('/')+[subitem['_path']])
                self.logger.debug("%s <- %s" %
                                  (subitem['_path'],subitem['_origin']))
                yield subitem
        self.logger.info("moved %d/%d" % (moved, len(items)))
                
        

    def getBacklinks(self, item):
        backlinks = {}
        text = item.get('text','')
        if not text:
            return backlinks
        base = item.get('_site_url')
        url = base + item.get('_path')
        
        tree = lxml.html.soupparser.fromstring(text)
        for element, attribute, rawlink, pos in tree.iterlinks():
            t = urlparse.urlparse(rawlink)
            fragment = t[-1]
            t = t[:-1] + ('',)
            rawlink = urlparse.urlunparse(t)
            link = urlparse.urljoin(url, rawlink)
            if link[-1] == '/':
                link = link[:-1]
            #override to get link text
            name = None
            if attribute == 'href':
                name = ' '.join(element.text_content().split())
            elif attribute == 'src':
                name = element.get('alt','')
            if name and link != url:
                backlinks.setdefault(link,[]).extend([(url,name)])
        return backlinks

