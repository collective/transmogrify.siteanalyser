
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
from transmogrify.pathsorter.treeserializer import TreeSerializer

"""
Guess Hide From Nav
===================

This blueprint will guess which folders should be hidden from the navigation tree.
It does this by one of three rules

1. Gather all links in the _template html left over after content extraction
and assume anything linked from outside the content should have their folders shown and 
anything else should be hidden. #TODO
2. Any folders with content found only via img links will also be hidden. #TODO
3. The condition to set to tree for the item to hide
"""

class GuessHideFromNav(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.template_key=options.get('template_key','_template')
        self.hide_img_folders = options.get('hide_img_folders','True')
        self.exclude_key = options.get('key','_exclude-from-navigation')
        self.condition = Condition(options.get('condition', 'python:False'),
                                   transmogrifier, name, options)
        self.logger = logging.getLogger(name)


    def __iter__(self):
        items = []
        defaultpages  = {}
        for item in self.previous:
            path = item.get('_path', None)
            if path is None:
                yield item
                continue
                
            if self.condition(item):
                item[self.exclude_key] = True
                items.append( item )
                self.logger.debug("%s: hide in nav due to condition" % (path))
            yield item
