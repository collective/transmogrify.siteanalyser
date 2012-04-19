
from zope.interface import implements
from zope.interface import classProvides

from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection

import logging

class TreeSerializer(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.default_pages = options.get('default_pages', 'index.html').split()
        self.default_containers = options.get('default_containers', 'Folder').split()
        self.name = name
        self.logger = logging.getLogger('%s(%s)'% (name, 'pathsorter'))

    def __iter__(self):
        items = {}
        for item in self.previous:
            if '_site_url' not in item or \
               '_path' not in item:
                yield item
            else:
                path = item['_path']
                base = item['_site_url']
                if path and path[0] == '/':
                    path = path[1:]
                items[base+path] = item

        added_folders = set({})
        added_index = set()
        # build tree
        items_keys = items.keys()
        
        items_keys.sort()
        
        for item in items_keys:
            item_fullurl = item
            item = items[item]

            # add root folder so we can set default page on it
            parts = ['']+item['_path'].split('/')
#            if parts[0] == '':
#                parts = parts[1:]

            basepath = ''
            parentpath = ''
            parent = items.get(item['_site_url'])
            for part in parts:
                basepath += part

                if item['_site_url']+basepath in items:
                    #case where folder has text
                    if parent and parent.get('text', None) is not None:
                        # move to default page and replace with folder
                        parentpath = parent['_path'].split('/')
                        for i in ['']+range(1,10000):
                            newname = "%s%s"%(self.default_pages[0],i)
                            newpath = '/'.join([p for p in parentpath+[newname] if p])
                            if item['_site_url']+newpath not in items:
                                break
                        parent['_path'] = newpath
                        items[item['_site_url']+newpath] = parent
                        parentpath = '/'.join([p for p in parentpath if p])
                        newparent = dict(
                                            _path     = parentpath,
                                            _site_url = item['_site_url'],
                                            _defaultpage = newname)
                        if basepath != '':
                            newparent['_type'] = self.default_containers[0]
                        else:
                            #special case for portal object
                            pass
                        items[item['_site_url']+parentpath] = newparent

                        self.logger.debug("treeserialize: moved folder to %s" %(parent['_path']))
                else:
                    # parent which hasn't had a folder added yet
                    newparent = dict(
                        _path     = basepath,
                        _type     = self.default_containers[0],
                        _site_url = item['_site_url'])
                    items[item['_site_url']+basepath] = newparent
                    self.logger.debug("adding folder %s" %(basepath))
                    added_folders.add(basepath)
                if basepath != item['_path']:
                    parent = items.get(item['_site_url']+basepath)
                    if basepath != '':
                        basepath += '/'

            #case item is a default page
            if parts and parent and parent.get('_defaultpage') is None and \
                parts[-1] in self.default_pages and \
                parent.get('_type') in self.default_containers:
                    parent['_defaultpage'] = parts[-1]
                    added_index.add(parent['_path'])
                    
                    # also in case we added the parent ourselves we need to give a sortorder
                    if parent.get('_sortorder', None) is None:
                        parent['_sortorder'] = item.get('_sortorder', None)

        self.logger.info("%d folders added. %d defaultpages set, %d items sorted" %
                         (len(added_folders), len(added_index), len(items)))


        # sort items based on which were found first ie sortorder, but also need to keep in tree order
        # create a key for each item which is a list of sortorder for of each of it's parents
        cur_sort_key = []
        class KeyHolder:
            def __init__(self, value):
                self.value = value
                self.created = value is None
            __repr__ = lambda self: str(self.value)
            __cmp__ = lambda x,y: cmp(x.value, y.value)
            
        treeorder = []
        for path in sorted(items.keys()):
            item = items[path]
            depth = item['_path'].count('/')+1
            sortorder = item.get('_sortorder', None)
            new_key_part = KeyHolder(sortorder)
            cur_sort_key = cur_sort_key[:depth-1] + [new_key_part]
            treeorder.append( (cur_sort_key, path, item) )

            #some parents we created so we give them smallest sortorder
            for keyholder in cur_sort_key[:-1]:
                if not keyholder.created:
                    continue
                if keyholder.value is None or sortorder < keyholder.value:
                    keyholder.value = sortorder


        treeorder.sort()

        for sortorder, path, item in treeorder:
            self.logger.debug('Order: %s: %s' % (sortorder, item['_path']))

        for sortorder, path, item in treeorder:
            yield item

