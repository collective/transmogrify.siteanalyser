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
        self.relinker = UrlTidy(transmogrifier, name, options, self.ouriter())
        self.field_expr=Expression(options.get('field_expr','python:None'), transmogrifier, name, options)
        self.field = options.get('field','').strip()
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
        moved = 0
        sitemaps = 0
        total = 0

        for item in self.previous:
            total += 1

            # find the sitemap

            path = item.get('_path')
            if not path:
                items.append( item )
                continue
            html = None
            for field in [self.field_expr(item)] + [self.field]:
                if not field:
                    continue
                html = item.get(field,'')
                if html:
                    break
            if not html:
                items.append( item )
                continue

            # analyse the site map
            base = item['_site_url']
            base_path = '/'.join(path.split('/')[:-1])
            sitemap = analyse_sitemap(base, base_path, html)
            if sitemap:
                sitemaps += 1
            newpaths = merge_sitemap(dict(sitemap), newpaths)
            #self.logger.debug("sitemap %s=%s"% (path,str(sitemap)))
            items.append( item )

        for item in items:
            path = item.get('_path')
            if path in newpaths:
                moved += 1
                origin = item.get('_origin')
                if not origin:
                    item['_origin'] = path
                item['_path'] = newpaths[path]
                self.logger.debug("%s <- %s" % (newpaths[path],path))
            elif path:
                #self.logger.debug("%s -> NOT FOUND" % (path))
                pass
            yield item

        self.logger.info("moved %d/%d from %d sitemaps" % (moved,total,sitemaps))




def merge_sitemap(sitemap, newpaths):
    # Problem is to merge two trees

    # We find a single common element.
    common = None
    for oldpath, newpath in sitemap.items():
        if newpaths.get(oldpath):
            common = oldpath
            break

    if not common:
        newpaths.update( sitemap)
        return newpaths

    # we have common element, now merge
    new1 = newpaths.get(common).split('/')
    new2 = sitemap.get(common).split('/')
    if new1 == new2:
        newpaths.update( sitemap)
        return newpaths

    # Pick the deepest /TopLevel/Crime and /Crime.
    # TODO what if conflict? e.g. /TopLevel/Crime and /AnotherLevel/Crime
    if len(new1) > len(new2):
        mergein = sitemap
        mergeto = newpaths
    else:
        mergein = newpaths
        mergeto = sitemap
    base = mergeto[common].split('/')[:-1]
    minus = len(mergein[common].split('/'))-1
    for oldurl, newurl in mergein.items():
        if newurl.startswith(mergein[common]):
            mergednew = '/'.join(base + newurl.split('/')[minus:])
            mergeto[oldurl] = mergednew
        else:
            mergeto[oldurl] = newurl


    return mergeto



def analyse_sitemap(base, base_path, html, use_text=True):
        newpaths = []
        node = fragment_fromstring(html, create_parent=True)
        parents = []
        depth = 0
        lastdepth = 0
        events = ("start", "end")
        context = etree.iterwalk(node, events=events)
        for action, elem in context:
            if action == 'start':
                id = None
                if elem.tag == 'a':
                    href = elem.attrib.get('href')
                    if not href:
                        continue
                    href = urljoin(base,href,allow_fragments=False)
                    if not href.startswith(base):
                        continue
                    path = href[len(base):]
                    if use_text and elem.text:
                        id = ' '.join(elem.text.split()).strip()
                    else:
                        id = path.split('/')[-1]

                    parents = [(d,p) for d,p in parents if d<depth]
                    parents = parents + [(depth,id)]
                    relpath = '/'.join([p for d,p in parents])
                    newpaths.append( (path, base_path +'/'+relpath) )
                    lastdepth = depth
                depth += 1
            elif action == 'end':
                depth -= 1
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