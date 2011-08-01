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

from __future__ import with_statement

import exceptions, os, signal, sys, time, user

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from oyepa import run_cmd_on_path
import pyinotify


from fslayer import read_pending_updates, write_pending_updates, readDocDirList, split_purename_and_tags_from_filename, add_tags_in_path_to_cache, remove_tags_in_path_from_cache_and_filename_from_pending_updates, isInternalOyepaOp

from generic_code import gui_excepthook

import cfg


doc_dirs = set()
wdd = {}
wm  = None
mask_dirs = 0

# this function access the file listing_doc_dirs_filepath (by default, 
# ~/.oyepa-dirs) and resets this process' inotify "watches" accordingly.

def update_watches():
    
    new_doc_dirs = readDocDirList()

    for removed_doc_dir in doc_dirs.difference(new_doc_dirs): 
        
        rr = wm.rm_watch(wdd[removed_doc_dir], rec=False)
        
        if rr[wdd[removed_doc_dir]]:
            
            print "[oyepa_filemon] stopped watching " + removed_doc_dir
            del wdd[removed_doc_dir]
            pass
        pass
    
    for added_doc_dir in new_doc_dirs.difference(doc_dirs): 
        
        ra = wm.add_watch(added_doc_dir, mask_dirs, rec=False)
        
        if ra[added_doc_dir] > 0: 
            
            wdd.update(ra)
            print "[oyepa_filemon] began watching " + added_doc_dir
            pass
        
        pass
    
    return new_doc_dirs

class Disappearance:
    
    def __init__(self, path, time):
        
        self.path = path
        self.time = time
        return
    pass

class PTmp(pyinotify.ProcessEvent):
    
    def __init__(self):
        
        # memory of recently renamed/deleted files, probably in the course of
        # an application's standard "save" process
        
        self.recently_deleted = []
        
        self.recently_moved = {} # self.recently_moved[pyinotify cookie] = Disappearance()
        
        return
    
    def resetDisappearancesMemory(self):
        
        current_time = time.time()
        
        # remove from cookie jar those which have timed out
        
        for cookie in self.recently_moved.copy():
            
            if current_time - self.recently_moved[cookie].time >= cfg.MAX_SAVE_PROCESS_DURATION:
                
                remove_tags_in_path_from_cache_and_filename_from_pending_updates(self.recently_moved[cookie].path)
                print "PERIODIC CHECK: found timed out path %s, removing its tags from tag cache"%self.recently_moved[cookie].path
                del self.recently_moved[cookie]
                pass
            pass
        
        # remove from paths to ignore those which have timed out
        
        for disappearance in self.recently_deleted[:]:
            
            if current_time - disappearance.time >= cfg.MAX_SAVE_PROCESS_DURATION:
                
                remove_tags_in_path_from_cache_and_filename_from_pending_updates(disappearance.path)
                print "PERIODIC CHECK: timed out path %s, removing its tags from tag cache"%disappearance.path
                self.recently_deleted.remove(disappearance)
                pass
            pass
        
        return
    
    
    def process_IN_CREATE(self, event):
        
        path = os.path.join(event.path, event.name)
        
        if isInternalOyepaOp(path): return # filemon mustn't interfere with file moving around conducted by the oyepa UI app
        
        if self.interesting_path(path) and not os.path.islink(path):
            
            print "file created, path " + path
            if not self.has_recently_disappeared(path): 
                
                add_tags_in_path_to_cache(path) # this path already exists in this doc_dir; update tag cache. What the user does next (in the doc tagger) is to simply *add/remove* tags on top of those; so the latter should already be in the cache
                self.call_gui_tagger(path)
                
            else: self.remove_from_recently_disappeared(path)
            pass
        
        return
    
    def process_IN_DELETE(self, event):
        
        path = os.path.join(event.path, event.name)
        
        if isInternalOyepaOp(path): return  # filemon mustn't interfere with file moving around conducted by the oyepa UI app
        
        if self.interesting_path(path):
            
            print "deleted %s, appending to recently_deleted"%path
            self.recently_deleted.append(Disappearance(path, time.time()))
            pass
        
        return
    
    def process_IN_MOVED_FROM(self, event):
        
        path = os.path.join(event.path, event.name)
        
        if isInternalOyepaOp(path): return  # filemon mustn't interfere with file moving around conducted by the oyepa UI app
        
        if self.interesting_path(path):         
            
            print "moved (FROM) %s, appending to recently_moved"%path
            self.recently_moved[event.cookie] = Disappearance(path, time.time())
            pass
        
        return
    
    def process_IN_MOVED_TO(self, event):
        
        path = os.path.join(event.path, event.name)
        
        if isInternalOyepaOp(path): return  # filemon mustn't interfere with file moving around conducted by the oyepa UI app
        
        if self.interesting_path(path):
            
            if self.has_recently_disappeared(path): 
                
                # doc went away, doc came back: all remains the same -- just prevent tags from being removed from cache
                
                print "moved_TO: %s has recently_disappeared and now reappeared, removing it from that list"%path
                
                self.remove_from_recently_disappeared(path)
                
            elif event.cookie in self.recently_moved: 
                
                # this operation was a doc being moved/renamed inside the doc repository (we don't know if it remained in *the same* doc dir). An update to the cache is already pending to remove the tags corresponding to its previous name; now we just need to ensure that we add its current (possibly different!) tags to its current (possibly different!) doc_dir
                
                print "moved_TO %s: renaming/movement within doc repository, adding tags (in this path) to cache"%path
                add_tags_in_path_to_cache(path)
                
            else:
                
                # file imported into doc_dir from outside; the user might want to tag it
                
                print "moved_TO %s: importing from outside doc repository, adding tags to cache and calling tagger"%path
                
                add_tags_in_path_to_cache(path) # this path already exists in this doc_dir; update tag cache. What the user does next (in the doc tagger) is to simply *add/remove* tags on top of those; so the latter should already be in the cache
                
                self.call_gui_tagger(path) 
                
                pass
            pass
        
        return
    
    def has_recently_disappeared(self, path):
        
        ret = path in [d.path for d in self.recently_moved.values()] or \
        path in [d.path for d in self.recently_deleted]
        
        return ret
    
    def remove_from_recently_disappeared(self, path):
        
        print "trying to remove %s from recently_disappeared lists"%path
        
        for cookie, disappearance in self.recently_moved.items():
            
            if disappearance.path == path:
                print "      found it, removing"
                del self.recently_moved[cookie]
                return
            pass
        
        for disappearance in self.recently_deleted[:]:
            
            if disappearance.path == path:
                print "      found it, removing"
                self.recently_deleted.remove(disappearance)
                return
            pass
        
        print "TROUBLE: couldn't find %s in recently_disappeared lists"%path
        return
    
    def interesting_path(self, path):
        
        return "/." not in path and "/#" not in path and not path.endswith("~")
    
    def call_gui_tagger(self, path):
        
        print "calling gui_tagger"
        run_cmd_on_path(cfg.OYEPA_GUI_FILENAME, path)
        return
    
    pass

# main() ################

def main():
    
    global doc_dirs
    global wdd
    global wm
    global mask_dirs
    
    listing_doc_dirs_filepath = os.path.join(user.home, cfg.FILENAME_LISTING_DOC_DIRS)
    
    # try to exit cleanly when sent a signal telling us to quit
    
    def handle_quit_signal(signum, frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, handle_quit_signal)
    signal.signal(signal.SIGHUP, handle_quit_signal)
    signal.signal(signal.SIGQUIT, handle_quit_signal)
    
    
    # check if another instance of oyepa_filemon is running
    
    if os.path.exists(cfg.FILEPATH_FILEMON_RUNNING):
        
        msg = "OYEPA: another instance of the file monitor is already running!\n"\
        "       Either stop it or, if you believe it is not really running, just manually remove %s to proceed."%cfg.FILEPATH_FILEMON_RUNNING
        
        print msg
        app = QApplication(sys.argv)
        QMessageBox.critical(None, sys.argv[0], msg)
        sys.exit(1)
        
    else: # otherwise, tell others I am here
        
        f = open(cfg.FILEPATH_FILEMON_RUNNING, "w")
        f.close()
        pass
    
    # setup dir watching
    
    mask_dirs = pyinotify.IN_CREATE | pyinotify.IN_DELETE |   \
    pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO
    
    wm = pyinotify.WatchManager()
    
    wdd = {}
    
    evProcessor = PTmp()
    notifier = pyinotify.Notifier(wm, evProcessor, timeout=5000)
    
    doc_dirs = set()
    
    print
    print "starting oyepa-filemon"
    
    # ironically, in an app using inotify the only reliable way I found to
    # monitor for changes to the file listing which dirs to watch involves
    # recording its mtime and stat()ing it regularly! : )
    
    prev_mtime = 0
    
    try:
        
        while True:
            
            # check if we should update the list of dirs we are watching
            # [if we simply call update_watches() every time, without checking
            # if it is necessary, at least on my laptop the HD will never go to 
            # sleep]
            
            if os.path.exists(listing_doc_dirs_filepath):
                
                st = os.stat(listing_doc_dirs_filepath)
                
                if st.st_mtime > prev_mtime:
                    
                    doc_dirs = update_watches()
                    prev_mtime = st.st_mtime
                    pass
                pass
            
            elif prev_mtime != -1:
                
                doc_dirs = update_watches() # will disable all watches
                prev_mtime = -1 # signals 'missing listing_doc_dirs_filepath'
                pass
            
            # now loop, prompting the user to tag any (seemingly) new docs in any of the doc_dirs
            
            evProcessor.resetDisappearancesMemory()
            
            notifier.process_events()
            
            if notifier.check_events():
                
                notifier.read_events()
                pass
            
            pass
        pass
    
    except (KeyboardInterrupt, Exception), instance:
        
        print "stopping oyepa-filemon..."
        
        notifier.stop()
        
        # perform pending updates (and remove any lying around "internal ops" file)
        
        update_files()
        
        # other stuff to do...
        
        if os.path.exists(cfg.FILEPATH_FILEMON_RUNNING): os.unlink(cfg.FILEPATH_FILEMON_RUNNING) # in case we were actually sent a signal
        
        print "stopped oyepa-filemon."
        
        if type(instance) != exceptions.KeyboardInterrupt: 
            
            app = QApplication(sys.argv)
            sys.excepthook = gui_excepthook
            raise
        pass
    return

if __name__ == "__main__": #and False:
    
    main()
    pass

