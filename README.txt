Introduction
============

Transmogrifier blueprints that look at how html items are linked to gather metadata
about items. They can help you restructure your content.


transmogrify.siteanalyser.urltidy
=================================
Will  normalize ids in urls to be suitable for adding to plone.

The following will tidy up the URLs based on a TALES expression ::

 $> bin/funnelweb --urltidy:link_expr="python:item['_path'].endswith('.html') and item['_path'][:-5] or item['_path']"

If you'd like to move content around before it's uploaded you can use the urltidy step as well e.g. ::

 $> bin/funnelweb --urltidy:link_expr=python:item['_path'].startswith('/news') and '/otn/news'+item['path'][5:] or item['_path']


transmogrify.siteanalyser.attach
================================
Find attachments which are only linked to from a single page. Attachments are merged into the
linking item either by setting keys or moving it into a folder.

The following will find items only referenced by one page and move them into
a new folder with the page as the default view. ::

 $> bin/funnelweb --attachmentguess:condition=python:True

or the following will only move attachments that are images and use ``index-html`` as the new
name for the default page of the newly created folder ::

  [funnelweb]
  recipe = funnelweb
  attachmentguess-condition = python: subitem.get('_type') in ['Image']
  attachmentguess-defaultpage = index-html



transmogrify.siteanalyser.title
===============================

You can automatically find better page titles by analysing backlink text ::

  [funnelweb]
  recipe = funnelweb
  titleguess-condition = python:True
  titleguess-ignore =
	click
	read more
	close
	Close
	http:
	https:
	file:
	img

transmogrify.siteanalyser.sitemapper
====================================
Rearrange content based on snippets of html arranged as a navigation tree or sitemap.
A navigation tree is a set of href links arranged in nested html.

Options
-------

field
  Name of a field from item which contains a sitemap

field_expr
  Expression to determine the field which contains a sitemap

condition
  Don't move this item

transmogrify.siteanalyser.hidefromnav
=====================================
If you want to hide content from navigation you can use `hideguess`

condition
  e.g. python:item['path']=='musthide'


transmogrify.siteanalyser.defaultpage
=====================================
To determine if an item is a default page for a container (it has many links
to items in that container, even if not contained in that folder), and then move
it to that folder.

Options
-------

mode
  'links' or 'path' (default=links).
  'links' mode uses links
  to determine if a item is a defaultpage of a subtree by looking at it's links.
  'path' mode uses parent_path expression to
  determine if an item is a defaultpage of that parent.

min_links
  If a page has as at least this number of links that point to content in a folder
  then move it there and make it the defaultpage. (default=2)

max_uplinks
  If a page has more than max_uplinks it won't be moved. (default=2)

parent_path
        Rule is defined by entered
        parent_path option which is expression with access to item,
        transmogrifier, name, options and modules variables.
        Returned value is used to find possible parent item by path. If found,
        item is moved to that parent item, parent item _defaultpage key is set
        appropriately, and we turn to processing another item in a pipeline. So
        the first item in pipeline will take precedence in case parent_path rule
        returns more than one item for the same parent.

condition
  default=python:True


transmogrify.siteanalyser.relinker
==================================
Help restructure your content.
If you'd like to move content from one path to another then in a
previous blueprints adjust the '_path' to the new path. Create a new field
called '_origin' and put the old path into that. Once you pass it through
the relinker all href, img tags etc will be changed in any html content where they
pointed to content that has since moved. All '_origin' fields will be removed
after relinking.