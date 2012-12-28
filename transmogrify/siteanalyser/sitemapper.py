__author__ = 'dylanjay'


from zope.interface import classProvides
from zope.interface import implements
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.utils import Matcher,Condition,Expression
import logging
from relinker import Relinker
from urltidy import UrlTidy
from lxml import etree
from lxml.html import fragment_fromstring
from urlparse import urljoin
import pprint

#INVALID_IDS = ['security']


"""
transmogrify.siteanalyser.sitemapper
====================================
Take navigation html such as a whole sitemap, breadcrumbs or navigation menus using nested links
and buildup a site structure and titles
for pages. This can then be used to cleanup urls and titles for items as well as hide content that shouldn't be
displayed in menus. This is useful for cleaning up sites with a flat url scheme such 'display?id=xxx' type sites.


Options:

:field:
  Name of a field from item which contains a sitemap or nested links

:field_expr:
  Expression to determine the field which contains a sitemap

:breadcrumb_field:
  Key of the field which contains breadcrumb style html. e.g. <a href="..">Folder</a> &gt; Item.

:folder-type:
  If set will ensure all parents in sitemap are of this Type, moving item to defaultpage if needed

:exclude-from-navigation-key:
  Will set this key to 'True' if this item is not found in the sitemap. Defaults to 'exclude-from-navigation'

:title-key:
  Update this field with the title taken from the sitemap if no title already exists

:path_sub:
  Newline seperated regular expressions and substitions to adjust paths so change where content is moved to

:condition:
  TAL expression which if false, don't move this item


"""

class SiteMapper(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.relinker = Relinker(transmogrifier, '%s'%name, options, self.ouriter())
        self.field_expr=Expression(options.get('field_expr','python:None'), transmogrifier, name, options)
        self.field = options.get('field','').strip()
        self.breadcrumb_field = options.get('breadcrumb_field','').strip()
        self.condition=Condition(options.get('condition','python:True'), transmogrifier, name, options)
        self.logger = logging.getLogger(name)
        self.options = options
        # if set will ensure all sitemap items are of this type, using defaultpage if needed
        self.folder_type = options.get('folder-type','Folder').strip()
        self.convert_to_folders = False
        self.exclusion = options.get('exclude-from-navigation-key', 'exclude-from-navigation')
        self.title_key = options.get('title-key','title')
        self.post_sub = [ s.strip() for s in options.get('path_sub', options.get('post-sub','')).split('\n') if s.strip()]

        self.name = name
        self.logger = logging.getLogger(name)


    def __iter__(self):
 #       for item in self.relinker:
        for item in self.ouriter():
            yield item

    def ouriter(self):

        self.logger.debug("condition=%s" % (self.options.get('condition', 'python:True')))
        items = []
        moved = 0
        sitemaps = 0
        total = 0
        # list of site maps which don't merge togeather
        unmerged = []

        defaultpage_parent = {}
        items_by_path = {}


        # first find the default pages
        for item in self.previous:
            total += 1

            # find the sitemap
            path = item.get('_path')
            if path is None:
                yield item
                continue



            if item.get('_defaultpage'):
                defaultpage_path = '/'.join([p for p in [item['_path'],item.get('_defaultpage')] if p])
                defaultpage_parent[defaultpage_path] = path
            items_by_path[item['_path']] = item

            items.append(item)

        for item in items:
            path = item.get('_path')
            # analyse the site map
            base = item['_site_url']
            path = defaultpage_parent.get(path,path)
            #base_path = '/'.join(path.split('/')[:-1])
            #if 'search/search.asp' in path:
            #    import pdb; pdb.set_trace()

            if self.breadcrumb_field and self.breadcrumb_field in item:
                html = item.get(self.breadcrumb_field, '')
                # assume all breadcrumbs start from /
                sitemap = self.analyse_sitemap(base, path, html,  defaultpage_parent, nested=False)
                # special case where path isn't in the breadcrumbs
                if path not in [p for p,n in sitemap]:
                    # we'll assume the last sitemap item is our parent
                    pass



                #self.logger.debug(pprint.pprint(sitemap))
                if sitemap:
                    sitemaps += 1
                unmerged = list(self.merge_sitemap(dict(sitemap), unmerged))


            html = None
            fields = self.field_expr(item)
            if type(fields) != type([]):
                fields = [fields]
            for field in fields + [self.field]:
                if not field:
                    continue
                html = item.get(field, '')
                if not html:
                    continue
                sitemap = self.analyse_sitemap(base, path, html, defaultpage_parent)

                #self.logger.debug(pprint.pprint(sitemap))
                if sitemap:
                    sitemaps += 1
                unmerged = list(self.merge_sitemap(dict(sitemap), unmerged))
                #self.logger.debug("sitemap %s=%s"% (path,str(sitemap)))
                #self.logger.debug(pprint.pprint(newpaths))



        # join remaining sitemaps together and remove duplicates
        newpaths = {}
        oldpaths = {}
        for sitemap in unmerged:
            for oldpath,newpath in sitemap.items():
                if newpath in oldpaths:
                    # two items have the same site map path :(
                    # pick the shortest one
                    if oldpath == oldpaths[newpath]:
                        continue
                    self.logger.warning("%s sitemap conflict (%s, %s)"%(newpath,oldpath, oldpaths[newpath]))
                    if len(oldpath.split('/')) < len(oldpaths[newpath].split('/')):
                        del newpaths[oldpaths[newpath]]
                        oldpaths[newpath] = oldpath
                        newpaths[oldpath] = newpath
                    else:
                        # leave existing path in there
                        oldpath = oldpaths[newpath]
                else:
                    oldpaths[newpath] = oldpath
                    newpaths[oldpath] = newpath

        for newpath, oldpath in sorted([(v,k) for k,v in newpaths.items()]):
            # Handle case where our parent is not a folder
            newparentpath = '/'.join(newpath.split('/')[:-1])
            oldparentpath = oldpaths.get(newparentpath)
            oldparent = items_by_path.get(oldparentpath)
            if oldparent is None:
                continue
            if '/' not in oldparentpath:
                continue
            if oldparent['_type'] != self.folder_type:
                # we have to convert the parent into a folder with a default page
                # we need to make it the

                oldparentpath, indexid = oldparentpath.rsplit('/',1)

                # is there an existing folder?
                newparent = items_by_path.get(oldparentpath)

                if newparent is None:
                    self.logger.debug("%s is breadcrumbparent, creating folder" % (oldpath, '/'.join([newparentpath,indexid])) )
                    newparent = dict(
                                    _path     = oldparentpath,
                                    _site_url = item['_site_url'],
#                                    title = newparentpath.split('/')[-1],
                                    _type = self.folder_type)
                    #update our indexes
                    items.append(newparent)
                    items_by_path[oldparentpath] = newparent
#                    self.logger.debug("'%s' created new folder"%item['_path'] )
                elif '_defaultpage' in newparent:
                    self.logger.debug("%s is breadcrumbparent but already has defaultpage %s" % (oldpath, '/'.join([newparentpath,newparent['_defaultpage']])) )
                    continue
                else:
                    #import pdb; pdb.set_trace()
                    self.logger.debug("%s is breadcrumbparent, setting as defaultpage %s" % (oldpath, '/'.join([newparentpath,indexid])) )

                newparent['_defaultpage'] = indexid

                newpaths[oldparentpath] = newparentpath
                oldpaths[newparentpath] = oldparentpath
                #origin = oldparent.get('_origin')
                #if not origin:
                #    newparent['_origin'] = path
                #else:
                #    newparent['_origin'] = origin

        self.logger.debug("==Merged Sitemap==")
        for newp, oldp in sorted([(v,k) for k,v in newpaths.items()]):
            self.logger.debug("%s (%s)"%(newp,oldp))
        self.logger.debug("==================")

        for item in items:

            path = item.get('_path')
            if not path:
                yield item
                continue
            if not self.condition(item):
                self.logger.debug("skipping %s (condition)" % path)
                yield item
                continue


            newpath = newpaths.get(path)
            #check if we're of the right type
            #import pdb; pdb.set_trace()
            matched = False
            if self.convert_to_folders and newpath and self.folder_type and item.get('_type') != self.folder_type:

                # create new folder so we ensure all sitemap items are folders

                newname = 'index'
                newparent = dict(
                                _path     = newpath,
                                _site_url = item['_site_url'],
                                title = newpath.split('/')[-1],
                                _defaultpage = newname,
                                _type = self.folder_type)
                origin = item.get('_origin')
                #if not origin:
                #    newparent['_origin'] = path
                #else:
                #    newparent['_origin'] = origin
                yield newparent
                if origin is None:
                    item['_origin'] = item['_path']
                item['_path'] = '/'.join([newpath,newname])
                self.logger.debug("'%s' created new folder"%item['_path'] )
                matched = True
            else:
                # move the item in any parent in the sitemap
                parents = path.split('/')
                parent_path = None
                for i in range(len(parents), 0, -1):
                    parent_path = '/'.join(parents[0:i])
                    if parent_path in newpaths:
                        # one of our parents is in the sitemap so we have to move
                        matched = True
                        break
                if matched:
                    origin = item.get('_origin')
                    if not origin:
                        item['_origin'] = path

                    #newp = newpaths[parent_path].split('/')
                    #oldp = parent_path.split('/')
                    if False and path == parent_path and len(newp) == len(oldp):
                        import pdb; pdb.set_trace()
                        # in this case we can use the old path and set the title based
                        # on the new path
                    else:
                        item['_path'] = path.replace(parent_path, newpaths[parent_path])
                    self.logger.debug("%s <- %s" % (item['_path'], path))
                    #item['_breadcrumb'] = item['_path'].split('/')
                    moved += 1
            if newpath and self.title_key and self.title_key not in item:
                item[self.title_key] = newpath.split('/')[-1]

            for sub in self.post_sub:
#                import pdb; pdb.set_trace()
                reg,sub = sub.split(num=1)
                match = re.match(reg, item['path'])
                if match:
                    item['path'] = match.sub(sub)
                    break

            if not matched:
                if self.exclusion:
                    item[self.exclusion] = 'True'
                self.logger.debug("%s didn't match the sitemap"%path)
            else:
                if self.exclusion:
                    item[self.exclusion] = 'False'
            yield item

        self.logger.info("moved %d/%d from %d sitemaps" % (moved,total,sitemaps))

    def merge_sitemap(self, sitemap, unmerged):


        for newpaths in unmerged:

            # We find a single common element.
            common_paths = []
            for oldpath, newpath in sitemap.items():
                if newpaths.get(oldpath):
                    common_paths.append(oldpath)

            #import pdb; pdb.set_trace()
            if not common_paths:
                yield newpaths
            else:
                #TODO should merge on all common
                common = common_paths[0]
                # we will form a single sitemap and then continue merging

                # we have common element, now merge
                new1 = newpaths.get(common).split('/')
                new2 = sitemap.get(common).split('/')

            #    print("**common: %s" % common)
            #    print("**newpaths: %s" % (newpaths.get(common)))
            #    print("**sitemap: %s" % (sitemap.get(common)))

                # we don't need to adjust to do the merge since both at the same level
                if new1 == new2:
                    sitemap.update(newpaths)
                    continue

        #        if newpaths[common][0] == '/':
        #            del sitemap[common]
        #            newpaths.update(sitemap)
        #            return newpaths
        #
        #        if sitemap[common][0] == '/':
        #            del newpaths[common]
        #            newpaths.update(sitemap)
        #            return newpaths

                # Pick the deepest /TopLevel/Crime and /Crime.
                # what if conflict? e.g. /TopLevel/Crime and /AnotherLevel/Crime
                if len(new1) > 1 and len(new2) > 1:
                    sitemap.update(newpaths)
                    continue


                # deal with /TopLevel/Common and Common (with Common/SubLevel)
                if len(new1) < len(new2):
                    mergein = sitemap
                    mergeto = newpaths
                    self.logger.debug('merge sitemaps on %s (%s<-%s)'%(common, new1, new2))
                else:
                    mergein = newpaths
                    mergeto = sitemap
                    self.logger.debug('merge sitemaps on %s (%s<-%s)'%(common, new2, new1))
                base = mergeto[common].split('/')[:-1]
                minus = len(mergein[common].split('/'))-1
                notmatched = {}
                for oldurl, newurl in mergein.items():
                    if newurl.startswith(mergein[common]):
                        mergednew = '/'.join(base + newurl.split('/')[minus:])

                        mergeto[oldurl] = mergednew
                    else:
                        notmatched[oldurl] = newurl
                if notmatched:
                    yield notmatched
                sitemap = mergeto

        # last sitemap remaining
        yield sitemap



    def analyse_sitemap(self, base, base_path, html, defaultpage_parent, use_text=True, nested=True):
            newpaths = []
            node = fragment_fromstring(html, create_parent=True)
            parents = []
            depth = 0
            lastdepth = 0
            found_paths = {}
            context = etree.iterwalk(node, events=("start", "end"))

            extra_text = []

            #Current state
            text = ''

            for action, elem in context:
                if action == 'start':
                    if elem.tag == 'a':
                        text = ''

                    depth += 1
                elif action == 'end':
                    # we are collecting text for our id
                    if use_text and elem.text:
                        text = ' '.join([text]+elem.text.replace('/',' ').split()).strip()

                    # collect text inside the a
                    if elem.tag == 'a':

                        href = elem.attrib.get('href')
                        url = ''
                        if href is not None:
                            url = urljoin(base,href,allow_fragments=False)
                        path = url[len(base):]
                        #replace the old_path with the parents if its a defualt page
                        path = defaultpage_parent.get(path, path)

                        if not url.startswith(base):
                            #it's an external link
                            pass
                        elif path == '':
                            # it's home, lets skip
                            pass
                        elif path in found_paths:
                            # duplicate entry, skip it
                            # we assume the first one is the better name
                            pass
                        else:
                            found_paths[path] = True
                            if not text:
                                id = path.split('/')[-1]
                            else:
                                id = text

                            if nested:
                                parents = [(d,p) for d,p in parents if d<depth]
                            parents = parents + [(depth,id)]
                            relpath = '/'.join([p for d,p in parents])
                            #if base_path:
                            #    relpath = '/'.join([base_path,relpath])

                            newpaths.append( (path, relpath) )
                            #newpaths.append( (path, relpath) )
                            lastdepth = depth
                    elif not isinstance(elem.tag, basestring):
                        # it's a comment
                        pass
                    elif text:
                        extra_text.append(text)

                    text = ''
                    if use_text and elem.tail:
                        text = ' '.join([text]+elem.tail.replace('/',' ').split()).strip()

                    if nested:
                        depth -= 1


            # special case: use unlinked text at end of breadcrumb for cur path
            # don't replace default page for this link due to way breadcrumbs work
            if not nested and len(newpaths):
                lastold, lastnew = newpaths[-1]
                if lastold != base_path:
                    if extra_text:
                        newpaths.append( (base_path, '/'.join([lastnew,extra_text[-1]]) ))
                    else:
                        # Need to include our link in there somewhere. We'll assume last part of breadcrumb is parent
                        oldid = base_path.split('/')[-1]
                        newpaths.append( (base_path, '/'.join([lastnew,oldid]) ))

            return newpaths

sitemap1 = """
<ul>
<li><a href="/asp/blah" class="">Toplevel</a></li>
<ul>
    <li><a href="/asp/index.asp?pgid=10652" class="">Crime</a></li>
    <li><a href="/asp/blah2" class="">Something Else</a></li>
</ul>
</ul>
"""


sitemap2 = """
<ul>
<li><a href="/asp/index.asp?pgid=10652" class="">Crime</a></li>
<ul>
    <li><a href="/asp/index.asp?pgid=10751" class="">Organised crime</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10933" class="">Investigating organised crime</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10752" class="">Paedophilia</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10791" class="">Relevant Queensland legislation</a></li>

        <li><a href="/asp/index.asp?pgid=10792" class="">Reporting sexual abuse</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10753" class="">Serious crime</a></li>

    <li><a href="/asp/index.asp?pgid=10754" class="">Proceeds of crime</a></li>

    <li><a href="/asp/index.asp?pgid=10755" class="">Crime prevention</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10765" class="">Major crime defined</a></li>
        <ul>
            <li><a href="/asp/index.asp?pgid=10757" class="">Gathering intelligence</a></li>
        </ul>
    </ul>
    <li><a href="/asp/index.asp?pgid=10936" class="">Case studies</a></li>
</ul>
<li><a href="/asp/index.asp?pgid=10658" class="">Misconduct</a></li>
<ul>
    <li><a href="/asp/index.asp?pgid=10764" class="">Complaints to the CMC</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10760" class="">What is misconduct?</a></li>

        <li><a href="/asp/index.asp?pgid=10770" class="">How we will deal with your complaint</a></li>

        <li><a href="/asp/index.asp?pgid=10772" class="">Types of complaints not handled by the CMC</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10758" class="">Reporting misconduct</a></li>

    <li><a href="/asp/index.asp?pgid=10756" class="">Building capacity to deal with misconduct</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10781" class="">Relevant publications</a></li>

        <li><a href="/asp/index.asp?pgid=10768" class="">Are you a CMC Liaison Officer?</a></li>

        <li><a href="/asp/index.asp?pgid=10841" class="">Facing the facts (guidelines)</a></li>

        <li><a href="/asp/index.asp?pgid=10895" class="">Whistleblowing research and advice</a></li>

        <li><a href="/asp/index.asp?pgid=10734" class="">Promoting Indigenous partnerships</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10779" class="">Misconduct prevention</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10915" class="">For local government</a></li>

        <li><a href="/asp/index.asp?pgid=10878" class="">Building ethical workplace cultures</a></li>

        <li><a href="/asp/index.asp?pgid=10849" class="">Conflicts of interest</a></li>

        <li><a href="/asp/index.asp?pgid=10863" class="">Codes of conduct</a></li>

        <li><a href="/asp/index.asp?pgid=10850" class="">Disposal of scrap and low-value assets</a></li>

        <li><a href="/asp/index.asp?pgid=10869" class="">Fraud and corruption control and integrated strategies</a></li>

        <li><a href="/asp/index.asp?pgid=10851" class="">Gifts and benefits</a></li>

        <li><a href="/asp/index.asp?pgid=10853" class="">Information security</a></li>

        <li><a href="/asp/index.asp?pgid=10879" class="">Integrity in leadership</a></li>

        <li><a href="/asp/index.asp?pgid=10880" class="">Internet and email</a></li>

        <li><a href="/asp/index.asp?pgid=10854" class="">Purchasing and tendering</a></li>

        <li><a href="/asp/index.asp?pgid=10881" class="">Recruitment and selection</a></li>

        <li><a href="/asp/index.asp?pgid=10882" class="">Risk management</a></li>

        <li><a href="/asp/index.asp?pgid=10883" class="">Secondary employment</a></li>

        <li><a href="/asp/index.asp?pgid=10855" class="">Sponsorships</a></li>

        <li><a href="/asp/index.asp?pgid=10856" class="">Use of official resources</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10836" class="">Hearings</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10910" class="">Public hearing Operation Tesco</a></li>

        <li><a href="/asp/index.asp?pgid=10908" class="">Public hearing to investigate alleged misuse of public
            money</a></li>
        <ul>
            <li><a href="/asp/index.asp?pgid=10909" class="">Submissions</a></li>
        </ul>
        <li><a href="/asp/index.asp?pgid=10888" class="">Public hearing into possible official misconduct</a></li>

        <li><a href="/asp/index.asp?pgid=10872" class="">Inquiry into Policing in Indigenous Communities: Overview</a>
        </li>
        <ul>
            <li><a href="/asp/index.asp?pgid=10889" class="">Terms of reference</a></li>

            <li><a href="/asp/index.asp?pgid=10890" class="">Submissions</a></li>

            <li><a href="/asp/index.asp?pgid=10891" class="">Public forum, Cairns</a></li>
        </ul>
        <li><a href="/asp/index.asp?pgid=10837" class="">Past hearings</a></li>
        <ul>
            <li><a href="/asp/index.asp?pgid=10839" class="">Gold Coast City Council</a></li>

            <li><a href="/asp/index.asp?pgid=10838" class="">CJC public hearings</a></li>
        </ul>
    </ul>
    <li><a href="/asp/index.asp?pgid=10937" class="">Case studies</a></li>
</ul>
<li><a href="/asp/index.asp?pgid=10662" class="">Witness protection</a></li>
<ul>
    <li><a href="/asp/index.asp?pgid=10663" class="">History</a></li>

    <li><a href="/asp/index.asp?pgid=10664" class="">Eligibility</a></li>

    <li><a href="/asp/index.asp?pgid=10666" class="">Legislation</a></li>

    <li><a href="/asp/index.asp?pgid=10665" class="">Training</a></li>
</ul>
<li><a href="/asp/index.asp?pgid=10739" class="">About the CMC</a></li>
<ul>
    <li><a href="/asp/index.asp?pgid=10932" class="">From the Chairperson</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10938" class="">13 July 2011</a></li>

        <li><a href="/asp/index.asp?pgid=10917" class="">11 April 2011</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10805" class="">Our jurisdiction</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10842" class="">What is a 'unit of public administration'?</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10736" class="">What we do</a></li>

    <li><a href="/asp/index.asp?pgid=10701" class="">What we cannot do</a></li>

    <li><a href="/asp/index.asp?pgid=10702" class="">How we operate</a></li>

    <li><a href="/asp/index.asp?pgid=10703" class="">The CMC's powers</a></li>

    <li><a href="/asp/index.asp?pgid=10707" class="">Accountability & leadership</a></li>

    <li><a href="/asp/index.asp?pgid=10704" class="">Legislation</a></li>

    <li><a href="/asp/index.asp?pgid=10700" class="">Our priorities</a></li>

    <li><a href="/asp/index.asp?pgid=10699" class="">Freedom of Information</a></li>

    <li><a href="/asp/index.asp?pgid=10896" class="">Right to information</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10906" class="">Disclosure Log</a></li>

        <li><a href="/asp/index.asp?pgid=10897" class="">Classes of accessible information</a></li>
        <ul>
            <li><a href="/asp/index.asp?pgid=10899" class="">About us</a></li>

            <li><a href="/asp/index.asp?pgid=10900" class="">Our services</a></li>

            <li><a href="/asp/index.asp?pgid=10901" class="">Our finances</a></li>

            <li><a href="/asp/index.asp?pgid=10902" class="">Our priorities</a></li>

            <li><a href="/asp/index.asp?pgid=10903" class="">Our decisions</a></li>

            <li><a href="/asp/index.asp?pgid=10904" class="">Our policies</a></li>

            <li><a href="/asp/index.asp?pgid=10905" class="">Our lists</a></li>
        </ul>
        <li><a href="/asp/index.asp?pgid=10898" class="">Accessing information under the RTI Act</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10698" class="">Frequently asked questions</a></li>

    <li><a href="/asp/index.asp?pgid=10694" class="">Contact us</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10695" class="">Contact form</a></li>

        <li><a href="/asp/index.asp?pgid=10843" class="">Tell us what you think about the website</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10706" class="">Information in other languages</a></li>

    <li><a href="/asp/index.asp?pgid=10918" class="">Our beginnings</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10877" class="">The Fitzgerald Inquiry</a></li>
    </ul>
</ul>
<li><a href="/asp/index.asp?pgid=10815" class="">Careers with the CMC</a></li>

<li><a href="/asp/index.asp?pgid=10766" class="">Media & Events</a></li>
<ul>
    <li><a href="/asp/index.asp?pgid=10767" class="">Media releases</a></li>

    <li><a href="/asp/index.asp?pgid=10797" class="">Media information on public inquiries</a></li>

    <li><a href="/asp/index.asp?pgid=10799" class="">The investigation process</a></li>

    <li><a href="/asp/index.asp?pgid=10798" class="">Media policy</a></li>

    <li><a href="/asp/index.asp?pgid=10801" class="">CMC Commissioners</a></li>
</ul>
<li><a href="/asp/index.asp?pgid=10743" class="">Publications</a></li>
<ul>
    <li><a href="/asp/index.asp?pgid=10935" class="">Annual reports</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10816" class="">Previous annual reports</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10928" class="">Strategic plans</a></li>

    <li><a href="/asp/index.asp?pgid=10806" class="">Brochures</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10857" class="">Fact sheets in HTML</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10818" class="">Building Capacity series</a></li>

    <li><a href="/asp/index.asp?pgid=10819" class="">Crime Bulletin series</a></li>

    <li><a href="/asp/index.asp?pgid=10829" class="">Discussion papers</a></li>

    <li><a href="/asp/index.asp?pgid=10830" class="">Investigation reports</a></li>

    <li><a href="/asp/index.asp?pgid=10831" class="">Misconduct prevention materials</a></li>

    <li><a href="/asp/index.asp?pgid=10862" class="">On the Right Track series</a></li>

    <li><a href="/asp/index.asp?pgid=10860" class="">Prevention Pointers</a></li>

    <li><a href="/asp/index.asp?pgid=10868" class="">Public Perceptions series</a></li>

    <li><a href="/asp/index.asp?pgid=10833" class="">Queensland Crime Commission reports</a></li>

    <li><a href="/asp/index.asp?pgid=10834" class="">Research and Issues Paper series</a></li>

    <li><a href="/asp/index.asp?pgid=10861" class="">Research Paper series</a></li>

    <li><a href="/asp/index.asp?pgid=10835" class="">Research reports</a></li>

    <li><a href="/asp/index.asp?pgid=10907" class="">Reviews</a></li>
</ul>
<li><a href="/asp/index.asp?pgid=10638" class="">Research</a></li>
<ul>
    <li><a href="/asp/index.asp?pgid=10911" class="">Review of Queensland's Prostitution Act</a></li>

    <li><a href="/asp/index.asp?pgid=10893" class="">Review of Queensland's police move-on powers</a></li>

    <li><a href="/asp/index.asp?pgid=10887" class="">Review of off-road motorbike noise laws</a></li>

    <li><a href="/asp/index.asp?pgid=10876" class="">Public nuisance inquiry</a></li>
</ul>
<li><a href="/asp/index.asp?pgid=10807" class="">Police & CMC</a></li>
<ul>
    <li><a href="/asp/index.asp?pgid=10929" class="">Review of the 'evade police' provisions</a></li>

    <li><a href="/asp/index.asp?pgid=10925" class="">Investigation into police misconduct on the Gold Coast</a></li>

    <li><a href="/asp/index.asp?pgid=10914" class="">Review of the police discipline system</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10927" class="">CMC power to seek review of QPS discipline decisions in
            QCAT</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10912" class="">Palm Island death in custody</a></li>

    <li><a href="/asp/index.asp?pgid=10919" class="">Use of Tasers by the Queensland Police Service</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10920" class="">CMC evaluation of Taser reforms</a></li>
    </ul>
    <li><a href="/asp/index.asp?pgid=10745" class="">History</a></li>

    <li><a href="/asp/index.asp?pgid=10804" class="">Working together</a></li>

    <li><a href="/asp/index.asp?pgid=10749" class="">Police Service Reviews</a></li>
    <ul>
        <li><a href="/asp/index.asp?pgid=10783" class="">PSR Commissioners</a></li>

        <li><a href="/asp/index.asp?pgid=10784" class="">Procedures for reviews</a></li>

        <li><a href="/asp/index.asp?pgid=10782" class="">FAQs</a></li>
    </ul>
</ul>
</ul>
"""

if __name__ == '__main__':
    m1 = analyse_sitemap('/','', sitemap1)
    m2 = analyse_sitemap('/','', sitemap2)
    newpaths = {}
    newpaths = merge_sitemap(dict(m1), newpaths)
    newpaths = merge_sitemap(dict(m2), newpaths)
    pprint.pprint( newpaths )