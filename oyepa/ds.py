#!/usr/bin/env python
#
# Copyright 2007, 2008, 2009, 2010 Manuel Arriaga
#
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

import os,sys

from fslayer import runQuery

def isItemUnder(path, directory):
    
    path = path.rstrip('/')
    directory = directory.rstrip('/')
    
    isUnder = len(path) > 0 and len(directory) > 0 and len(path) > len(directory) and \
    path.startswith(directory) and path[len(directory)] == '/'
    
    return isUnder

def makePathRelative(path):
    
    cwd = os.getcwd().rstrip('/')
    relPath = path
    
    if isItemUnder(path, cwd): relPath= path[len(cwd)+1:]
    return relPath

# main()

if len(sys.argv) == 2 and sys.argv[1] in ("-h","--help"):
    
    print "usage: ds.py keyword1 [keyword2 ...]"
    print "       ds.py keyword1 [keyword2 ...] dir1/ [dir2/ ...]"
    print "       ds.py -u                     show untagged docs"
    print "       ds.py -u  dir1/ [dir2/ ...]"
    print "notice that dir names MUST end with a trailing slash."
    
    sys.exit(0)
    pass

if len(sys.argv) == 2 and sys.argv[1] == "-u":
    
    matches = runQuery(None, None, sys.argv[2:] if len(sys.argv) > 2 else None, listUntagged=True)
    
else:
    
    keywords = []
    dirs = []
    
    sep = 1
    for sep in range(1,len(sys.argv)):
        if sys.argv[sep].endswith('/'): break
        pass
    else: sep = len(sys.argv)
    
    keywords = sys.argv[1:sep]
    dirs = sys.argv[sep:]
    
    #if len(dirs) == 0 or dirs == None: dirs = [os.getcwd()] enabling this line makes ds, by default, operate on the cwd
    
    dirs = map(lambda s: s.rstrip('/'), dirs)
    
    matches = runQuery(keywords, None, dirs) # missing support for specifying acceptable extensions from cmd line
    pass

for doc in matches: print makePathRelative(doc.path) 
