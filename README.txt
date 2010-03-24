Introduction
============

Transmogrifier blueprints that look at how html items are linked to gather metadata
about items.

transmogrify.siteanalyser.defaultpage
  Determines an item is a default page for a container if it has many links
  to items in that container. 

transmogrify.siteanalyser.relinker
  Fix links in html content. Previous blueprints can adjust the '_path' and set the original
  path to '_origin' and relinker will fix all the img and href links. It will also normalize
  ids.

transmogrify.siteanalyser.attach
  Find attachments which are only linked to from a single page. Attachments are merged into the
  linking item either by setting keys or moving it into a folder.

transmogrify.siteanalyser.title
  Determine the title of an item from the link text used.
