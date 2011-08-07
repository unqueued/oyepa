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

import os, user, pickle,re,stat, shutil,time,fcntl

import cfg


# CODE #####

re_filename = re.compile("^(.*?) ?(?:\[(.*)\])?(?:\\.\w*)?$")

assert(cfg.TIMESTAMP_TO_USE in ("ctime", "atime", "mtime"))

# Terminology. Given
#
# filename = 'document1[tag1,tag2].txt'
#
# we define
#
# purename = 'document1'
# docname  = 'document1[tag1,tag2]'
# ext      = 'txt'


########################


# This class is used to store the metadata for a doc together (i) its path and (ii) a flag
# which indicates whether the current metadata for this doc is more recent than that inscribed
# into its path (in which case, the metadata is contained in the cfg.pending_updates_filename file
# in the doc_dir containing this doc)

class Doc:
    
    def __init__(self, path, docname, extension, timestamp=None, metadataMoreRecentThanFilename = False):
        
        self.path = path.rstrip('/')
        self.docname = docname # this is the filename MINUS the [dot+]extension; ie, it INCLUDES THE TAGS STRING
        self.extension = extension
        self.timestamp = timestamp
        self.metadataMoreRecentThanFilename = metadataMoreRecentThanFilename
        return
    
    pass


class LockFile:
    
    def __init__(self, fileObject, path): 
        self.fileObject = fileObject
        self.path = path
        return
    
    pass

# returns a LockFile object (see above) of the lock file at lockfilepath or None
# (in case the wait for the lock times out). If exclusiveLock==False,
# tries to acquire a shared lock instead (suitably for concurrent reads
# but no write). timeout==None makes this function block (possibly forever)
# until the lock becomes available.

def acquire_lock(lockfilepath, timeout, exclusiveLock=True, interval_between_attempts_to_acquire = 0.2):
    
    lock_file = open(lockfilepath, "w")
    
    start_time = time.time()
    
    while timeout == None or time.time() - start_time < timeout:
        
        try: fcntl.flock(lock_file.fileno(), (fcntl.LOCK_EX if exclusiveLock else fcntl.LOCK_SH) | (fcntl.LOCK_NB if timeout != None else 0))
        
        except IOError: 
            
            #print "failed to get lock, will wait..."
            time.sleep(interval_between_attempts_to_acquire)
            
        else: 
            
            #print "got lock!"
            return LockFile(lock_file, lockfilepath)
        
        pass
    
    else: 
        
        #print "timed out, quitting!"
        return None
    
    pass

# arg is the LockFile object returned by acquire_lock(). Returns True if
# lock was released successfully, False otherwise

def release_lock(lockfile_object):
    
    try: fcntl.flock(lockfile_object.fileObject.fileno(), fcntl.LOCK_UN)
    
    except IOError:
        
        #print "couldn't release lock"
        retval = False
        
    else: 
        
        #print "released lock"
        retval = True
        
    finally: 
        lockfile_object.fileObject.close()
        try: os.unlink(lockfile_object.path)
        except: pass
        pass
    
    return retval

def acquireInternalOpsFileLock(exclusiveLock = True):
    
    return acquire_lock(os.path.join(user.home, cfg.oyepa_internal_ops_lockfilename), cfg.TIMEOUT_ON_WAITING_FOR_LOCK, exclusiveLock)


def acquireTagCacheFileLock(docDir, exclusiveLock = True):
    
    return acquire_lock(os.path.join(docDir,cfg.tag_cache_lockfilename), cfg.TIMEOUT_ON_WAITING_FOR_LOCK, exclusiveLock)


def acquirePendingUpdatesFileLock(docDir, exclusiveLock = True):
    
    return acquire_lock(os.path.join(docDir,cfg.pending_updates_lockfilename), cfg.TIMEOUT_ON_WAITING_FOR_LOCK, exclusiveLock)

# this function reads from the on-disk configuration file which doc dirs we
# should be operating on. It is called when this module is initialized
# to set the global var doc_dirs (see EOF).

# [UPDATE!] Tibor Csogor [tibi@tiborius.net] contributed much of the code 
# in this function, modifying it so that
#
# (i) entries in the config file ending with "/*" are understood as requests
#     to watch that directory *and all directories underneath it*, recursing
#     all the way down. Eg, a line "/home/user/project/*" will setup watches
#     on /home/user/project *and all directories beneath it (including
#     /home/user/project/abc/def/ghj).
# (ii) the tilde is now understood as referring to the user's home dir.
#      So, you can simply add a dir inside your home dir by adding the line
#      "~/project" to the config file.

def readDocDirList():
    
    dirlist_path = os.path.join(user.home, cfg.FILENAME_LISTING_DOC_DIRS)
    
    new_doc_dirs = set()
    
    if not os.path.exists(dirlist_path): return [] # nothing for us to do here
    
    with open(dirlist_path, "r") as f: 
        
        dirLines = f.readlines()
        pass
    
    raw_doc_dirs = set()
    
    for i in dirLines:
        
        i = i.strip()
        
        if i == '/' or i == '/*':
            
            print "WARNING: ignoring request to watch '/'!"
            pass
        
        i = i.rstrip('/')
        
        if len(i) == 0:
            
            continue
        
        i = os.path.expanduser(i)
        
        if not i.startswith('/'):
            
            i = os.path.join(user.home, i)
            pass
        
        raw_doc_dirs.add(unicode(i, 'utf-8'))
        
        pass
    
    new_doc_dirs = set()
    
    for pth in raw_doc_dirs:
        
        d = pth
        
        if pth.endswith('*'):
            
            d = pth[:-2] # we remove TWO characters, '/*'
            pass
        
        if not os.path.isdir(d):
            
            print ("WARNING: ignoring request to watch '%s': not a directory!"% d)
            continue
        
        if pth.endswith('*'):
            
            os.path.walk(d, dirVisitor, new_doc_dirs) # this is NOT the same as os.walk(). The 'dirVisitor' function is defined below, it merely adds all (sub)dirs it finds to the set of doc_dirs. new_doc_dirs, the last element in this list of arguments, is passed as the first argument of function dirVisitor [dirVisitor merely .add()s each (sub)dir it finds to that set.]
            
        else:
            
            new_doc_dirs.add(d)
            pass
        pass
    
    return new_doc_dirs


def dirVisitor(new_doc_dirs, dirname, names): # helper function used by readDocDirList(); see above
    
    new_doc_dirs.add(dirname)
    return

# This function provides basic exclusion rules for filenames

def should_skip(filename):
    
    return filename[0] in ('.','#') or filename[len(filename)-1] =='~' or filename in cfg.FILENAMES_TO_IGNORE

def validDocName(s):
    
    return len(s) > 0 and not ("[" in s or "]" in s or "/" in s)

def validTag(s):
    
    return len(s) > 0 and not ("," in s or "[" in s or "]" in s or "/" in s)


# Allows the GUI module to find out which doc_dirs we are operating on.
# NOTE: simply accessing "doc_dirs" (after "from fslayer import *") IS 
# BAD, since it will return the list as it was at the time if the import
# statement

def getDocDirs(): return doc_dirs


# returns a triplet containing (purename, list of tags, metadata is more recent
# than that in filename).

# Returns None in case of an error (arg outside of any doc_dir).

def getCurrentPureNameAndTagsForDoc(path):
    
    doc_dir, arg_filename = \
    os.path.split(os.path.abspath(path.rstrip('/')))
    
    if doc_dir not in doc_dirs: return None,None,None
    
    updates_dic = read_pending_updates(doc_dir)
    
    current_virtual_filename = \
    updates_dic[arg_filename] if arg_filename in updates_dic else arg_filename
    
    purename, tags = split_purename_and_tags_from_filename(current_virtual_filename)
    
    return purename, tags, current_virtual_filename != arg_filename



def split_docname_ext(filename):
    
    filename = filename.lower()
    docname = filename
    ext = None
    
    if '.' in filename:
        dot = filename.rindex('.')
        if dot+1 < len(filename) and '[' not in filename[dot:] and ']' not in filename[dot:]:
            ext = filename[dot+1:]
            docname = filename[:dot]
            pass
        pass
    return docname, ext


# Argument can be either a filename or a docname (since we 
# accept filenames without extension, a docname is always
# an acceptable filename).
# Returns (purename, list of tags).
#
# If the second, optional arg is set to True, then words (len>=3) found in
# the purename will also be included in the list of 'tags' we return.
#
# NOTE! It is important that this function only includes words in purename as tags
# when called from runQuery and rebuildTagCache. The rest of the code should only get
# the "real" tags (eg, the renameTag function).

def split_purename_and_tags_from_filename(filename, includeWordsInPurenameAsTags = False):
    
    tags = []
    
    purename, tag_str = re.match(re_filename, filename).groups()
    
    if tag_str != None: tags = [tag.strip() for tag in tag_str.lower().split(",")]
    
    if includeWordsInPurenameAsTags:
        
        fake_tags_from_purename = purename.lower().split()
        
        fake_tags_from_purename = map(lambda i: i.strip(':').strip(',').strip('-').strip('!').strip('(').strip(')'), fake_tags_from_purename)
        
        fake_tags_from_purename = filter(lambda i: len(i) > 2 and i.isalpha() and i.lower() != "and", fake_tags_from_purename)
        
        tags.extend(set(fake_tags_from_purename).difference(tags)) # make sure we don't add duplicates
        
        pass
    
    return purename, tags

def read_tag_cache(doc_dir, mustGetLock=True):
    
    tags_count = {}
    
    # by default we get a shared ("concurrent reads") lock; however, when called
    # from inside update_tag_cache() we don't get any (since that function already
    # has a write lock)
    
    if mustGetLock: lock_file = acquireTagCacheFileLock(doc_dir, exclusiveLock = False)
    
    try:
        filepath = os.path.join(doc_dir, cfg.tag_cache_filename)
        
        if os.path.exists(filepath):
            
            with open(filepath, "rb") as tag_cache_file:
                
                tags_count = pickle.load(tag_cache_file)
                pass
            pass
        pass
    
    finally: 
        
        if mustGetLock: release_lock(lock_file)
        pass
    
    return tags_count

def update_tag_cache(doc_dir, origTags, newTags):
    
    #print "doc_Dir: " + str(doc_dir) + "; origtags: " + str(origTags) +  "; newtags: " + str(newTags)
    
    if origTags == newTags: return # nothing to be done here
    
    # get an exclusive ("write") lock
    
    lock_file = acquireTagCacheFileLock(doc_dir)
    
    try: 
        # read tags_count for this dir from the disk
        
        tags_count = read_tag_cache(doc_dir, mustGetLock=False)
        
        # update the tags_count
        
        for tag in set(newTags).difference(origTags):
            if tag in tags_count: tags_count[tag] += 1
            else: tags_count[tag] = 1
            pass
        
        for tag in set(origTags).difference(newTags):
            if tag in tags_count: 
                tags_count[tag] -= 1
                if tags_count[tag] <= 0: del tags_count[tag]
                pass
            pass
        
        # write it to disk
        
        with open(os.path.join(doc_dir, cfg.tag_cache_filename), "wb") as tag_cache_file:
            
            pickle.dump(tags_count, tag_cache_file)
            pass
        pass
    
    finally: release_lock(lock_file)
    
    return

# Read the updates pending for the docs contained in the dir named in its arg.

def read_pending_updates(doc_dir):
    
    updates_dic = {}
    
    filepath = os.path.join(doc_dir, cfg.pending_updates_filename)
    
    lock_file = acquirePendingUpdatesFileLock(doc_dir, exclusiveLock = False)
    
    try:
        
        if os.path.exists(filepath):
            
            with open(filepath, "rb") as update_file:
                
                updates_dic = pickle.load(update_file)
                pass
            pass
        pass
    
    finally: release_lock(lock_file)
    
    return updates_dic


# Writes to disk the updates pending for the docs contained in the dir named in its arg

def write_pending_updates(doc_dir, updates_dic):
    
    pending_updates_path = os.path.join(doc_dir, cfg.pending_updates_filename)
    
    lock_file = acquirePendingUpdatesFileLock(doc_dir)
    
    try:
        
        with open(pending_updates_path, "wb") as pending_updates_file:
            
            pickle.dump(updates_dic, pending_updates_file)
            pass
        pass
    
    finally: release_lock(lock_file)
    
    return


# puts together a filename from all the metadata provided in its args.
# Returns None if filename would be too long. Notice that first arg
# is a *purename*, not a docname.

def assemble_filename_from_metadata(purename, tags, extension):
    
    new_filename = purename
    
    if len(tags) > 0:
        
        new_filename += '['
        for t in tags: new_filename += t + ", "
        new_filename = new_filename.rstrip(", ")
        new_filename += ']'
        pass
    
    if extension != None and len(extension) > 0:
        
        new_filename += '.' + extension
        pass
    
    return new_filename if len(new_filename) <= cfg.MAX_FILENAME_LEN else None



# 'purename' and 'tags' are the NEW (pure)name and tags to be applied
# to this doc. in case of error returns an error message (string), otherwise None

def tagDoc(path, purename, newTags, origTags):
    
    doc_dir, current_filename_in_fs = \
    os.path.split(os.path.abspath(path.rstrip('/')))
    
    assert(doc_dir in doc_dirs), "[oyepa BUG] tagDoc called with a path which does not point into a doc_dir!"
    
    extension = split_docname_ext(current_filename_in_fs)[1]
    
    new_filename = assemble_filename_from_metadata(purename, newTags, extension)
    
    if new_filename == None: return "Trouble: filename would be too long"
    
    
    updates_dic = read_pending_updates(doc_dir)
    
    # this copy of the updates_dic is used to find out if new_filename is
    # already reserved for _some other doc_ which is pending a rename
    
    updates_dic_for_all_other_docs = updates_dic.copy()
    
    if current_filename_in_fs in updates_dic_for_all_other_docs: del updates_dic_for_all_other_docs[current_filename_in_fs]
    
    if (current_filename_in_fs != new_filename and os.path.exists(os.path.join(doc_dir, new_filename))) or \
    (new_filename in updates_dic_for_all_other_docs.values()): 
        
        # 1st test means that a file/dir holding a doc OTHER THAN THE ONE WE ARE TAGGING already exists. Actually, this places a minor
        # artificial constraint: this function will fail even if the file/dir which already exists is simply a PREVIOUS incarnation of another doc,
        # which will be renamed soon. This shouldn't be a showstopper in the majority of cases, and prevents possible confusion when we
        # perform the updates at the time the filemon shuts down (ie, we would have to be careful to first rename that other, already existing
        # doc before renaming the one we are now tagging to its new name).
        
        # 2nd test means that this new_filename is already defined as the new name for _some other_ (hence the use of a copy of the updates_dic from which the current_filename_in_fs entry has been removed) doc pending a rename
        
        return "Trouble: a name collision occurred!\nPath: %s"%os.path.join(doc_dir, new_filename) # can't do, name is taken (by some other doc, otherwise previous branch would have been run)
    
    elif current_filename_in_fs == new_filename:
        
        if current_filename_in_fs in updates_dic: # this test IS necessary, because the GUI might call tagDoc without any changes to the metadata having occurred
            
            del updates_dic[current_filename_in_fs] # doc's metadata has reverted to its previous form inscribed into its path
            pass
        pass
    
    else: updates_dic[current_filename_in_fs] = new_filename
    
    write_pending_updates(doc_dir, updates_dic)
    
    update_tag_cache(doc_dir, origTags, newTags)
    return


# returns a list of 'Doc' objects describing the matching docs. In the case
# of files without an extension, their Doc.extension will be None. In the case
# of dirs without an extension, their Doc.extension will be set to FAKE_EXTENSION_FOR_DIRS.
# (Both files as well as dirs with an extension will be treated in the same way.
# Calling code should not discriminate between them, either.) Code which calls this
# function should interpret all these possible values correctly.

def runQuery(keywords, extensions, dirs, listUntagged=False):
    
    matches = []
    
    if keywords   != None: keywords = [kw.strip().lower() for kw in keywords]
    if extensions != None: extensions = [e.strip().lower() for e in extensions]
    
    if type(extensions) == list and len(extensions) == 0: extensions = None
    if type(keywords) == list and len(keywords) == 0:   keywords   = None
    
    if dirs == None or len(dirs) == 0: dirs = doc_dirs
    
    dirs = map(lambda d: os.path.abspath(d).rstrip('/'), dirs) # the cmd line util, ds, might pass us relative paths. And in the tight loop below profiling showed that a call to os.path.join() added .5 secs on my machine for each additional 10,000 docs
    
    for doc_dir in dirs:
        
        updates_dic = read_pending_updates(doc_dir)
        
        filenames = set(os.listdir(doc_dir))
        filenames.difference_update(updates_dic.keys()) 
        filenames.update(updates_dic.values())
        
        # this dic is used to retrieve the path to the actual file of
        # docs which had their metadata updated (ie, the new metadata
        # leaves in the file holding pending updates, while the path storing
        # the doc reflects previous metadata)
        
        rev_updates_dic = {}
        
        for (old,recent) in updates_dic.items():
            rev_updates_dic[recent]=os.path.join(doc_dir,old)
            pass
        
        for filename in filenames:
            
            if should_skip(filename): continue
            
            # if this is a 'recent' file (meaning no file with this filename 
            # actually exists in the filesystem, yet), then we need to get
            # the real path for this doc: -
            
            if filename in rev_updates_dic: 
                
                path = rev_updates_dic[filename] # this is correct, dict value really is a path (not a filename); see above
                metadataMoreRecentThanFilename = True
                
            else: 
                path = doc_dir + '/' + filename
                metadataMoreRecentThanFilename = False
                pass
            
            docname, ext = split_docname_ext(filename)
            
            try:
                st = os.stat(path)
                isdir = stat.S_ISDIR(st[stat.ST_MODE])
                timestamp = getattr(st, "st_" + cfg.TIMESTAMP_TO_USE)
                
            except OSError: 
                isdir = None
                timestamp = None
                pass
            
            if ext == None and isdir: ext= cfg.FAKE_EXTENSION_FOR_DIRS # to directories without an extension (e.g., "album") we give this "artificial" extension
            
            if (extensions == None or (ext != None and ext.lower() in extensions) or (cfg.extensionlessDirsAlwaysMatch and ext == cfg.FAKE_EXTENSION_FOR_DIRS)) and \
            ( (listUntagged and '[' not in docname) or (not listUntagged and keywords == None) or (not listUntagged and \
            len(filter(lambda kw: kw in docname, keywords)) == len(keywords))):
                
                matches.append(Doc(path=path, docname=docname, extension=ext, timestamp=timestamp, metadataMoreRecentThanFilename=metadataMoreRecentThanFilename))
                pass
            pass
        pass
    
    if   cfg.SORT_RESULTS_BY == "timestamp": matches.sort(key= lambda d: d.timestamp, reverse=True)
    elif cfg.SORT_RESULTS_BY == "name":    matches.sort(key= lambda d: d.docname.lower())
    else: assert False, "SORT_RESULTS_BY SET TO INVALID VALUE!"
    
    return matches


# Returns a set containing all tags

def getAllTags(): 
    
    # no need for tag cache lock(s), we get one inside read_tag_cache
    
    allTags = set()
    
    for doc_dir in doc_dirs:
        
        filepath = os.path.join(doc_dir, cfg.tag_cache_filename)
        
        if not os.path.exists(filepath): rebuildTagCache(doc_dir)
        
        tags_count = read_tag_cache(doc_dir)
        
        allTags.update(tags_count.keys())
        pass
    
    return allTags


def removeTag(tag): renameTag(tag, None) # see renameTag...

# It is the caller's task to check whether this will cause two tags
# to be merged (ie, whether newTag already exists).

# if newTag is set to None, then the tag named in the first arg is removed (see removeTag implementation above)

# In case of error, an error message (string) is returned. Otherwise, you get back None.

def renameTag(oldTag, newTag):
    
    if newTag != None: newTag = newTag.lower().strip()
    
    for doc_dir in doc_dirs:
        
        updates_dic = read_pending_updates(doc_dir)
        
        filenames = set(os.listdir(doc_dir))
        filenames.difference_update(updates_dic.keys()) 
        filenames.update(updates_dic.values())
        
        # this dic is used to retrieve the path to the actual file of
        # docs which had their metadata updated (ie, the new metadata
        # leaves in the file holding pending updates, while the path storing
        # the doc reflects previous metadata)
        
        rev_updates_dic = {}
        
        for (old,recent) in updates_dic.items():
            rev_updates_dic[recent]=os.path.join(doc_dir,old)
            pass
        
        for filename in filenames:
            
            if should_skip(filename): continue
            
            # if this is a 'recent' file (meaning no file with this filename 
            # actually exists in the filesystem, yet), then we need to get
            # the real path for this doc: -
            
            if filename in rev_updates_dic: 
                
                path = rev_updates_dic[filename]
                
            else: path = os.path.join(doc_dir, filename)
            
            purename, origTags = split_purename_and_tags_from_filename(filename)
            
            if oldTag not in origTags: continue # nothing to do here, move along
            
            newTags = []
            
            for tag in origTags:
                
                if tag == oldTag and newTag != None and newTag not in origTags: newTags.append(newTag)
                elif tag != oldTag: newTags.append(tag)
                pass
            
            retval = tagDoc(path, purename, newTags, origTags)
            
            if type(retval) == str: return retval # error, abort
            
            pass
        pass
    
    return None


# Rebuilds the tag cache files in all doc-dirs. If arg is None,
# operates on all doc_dirs

def rebuildTagCache(arg=None):
    
    if arg == None: dirs = doc_dirs
    else: dirs = [arg]
    
    for doc_dir in dirs:
        
        lock_file = acquireTagCacheFileLock(doc_dir) # get write lock
        
        try: 
            
            tags_count = {}
            
            updates_dic = read_pending_updates(doc_dir)
            
            filenames = set(os.listdir(doc_dir))
            filenames.difference_update(updates_dic.keys()) 
            filenames.update(updates_dic.values())
            
            for filename in filenames:
                
                if should_skip(filename): continue
                
                tags = split_purename_and_tags_from_filename(filename, cfg.includeWordsInPurenameAsTags)[1]
                
                for tag in tags:
                    if tag in tags_count: tags_count[tag] += 1
                    else: tags_count[tag] = 1
                    pass
                pass
            
            # write it to disk
            
            with open(os.path.join(doc_dir, cfg.tag_cache_filename), "wb") as tag_cache_file:
                
                pickle.dump(tags_count, tag_cache_file)
                pass
            pass
        
        finally: release_lock(lock_file)
        pass
    
    return




# by default secures a "read"/shared lock; but it might also be called from
# code which already has a write/exclusive lock on the internal ops file, hence
# the arg

def readInternalOps(mustGetLock=True):
    
    if mustGetLock: lock_file = acquireInternalOpsFileLock(exclusiveLock = False) # this one needs a share ("concurrent reads") lock
    
    try: 
        
        internalOps = []
        
        oyepa_internal_ops_filepath = \
        os.path.join(user.home, cfg.oyepa_internal_ops_filename)
        
        if os.path.exists(oyepa_internal_ops_filepath):
            
            with open(oyepa_internal_ops_filepath, "rb") as f:
                
                internalOps = pickle.load(f)
                pass
            pass
        
        pass
    
    finally: 
        
        if mustGetLock: release_lock(lock_file)
        pass
    
    return internalOps

# returns the time of our (meaning the "client"/GUI code, as opposed to the 
# filemon) last modification to the internalOps file. Calling code should pass
# the mtime we return to waitOnInternalOpsCleared(); the latter
# function will call removeFromOyepaInternalOps if the filemon hasn't shown up
# on time to demonstrate it has learnt which paths are being manipulated through
# internal operations)
#
# Arg can be either a path or a list of paths


def addToOyepaInternalOps(argPath_s):
    
    paths = []
    
    if type(argPath_s) == str: paths.append(argPath_s) # important, never extend() a list of str with a str argument (individual chars end being inserted, each as an item of its own)
    elif type(argPath_s) == list: paths.extend(argPath_s)
    else: assert False, "Invalid arg passed to addToOyepaInternalOps()"
    
    paths = [p.rstrip('/') for p in paths]
    
    lock_file = acquireInternalOpsFileLock() # this one needs an exclusive ("write") lock
    
    try: 
        
        internalOps = readInternalOps(mustGetLock=False)
        
        internalOps.extend(paths)               
        
        oyepa_internal_ops_filepath = \
        os.path.join(user.home, cfg.oyepa_internal_ops_filename)
        
        with open(oyepa_internal_ops_filepath, "wb") as f:
            
            pickle.dump(internalOps, f)
            pass
        
        pass
    
    finally: release_lock(lock_file)
    
    return os.stat(oyepa_internal_ops_filepath).st_mtime

def removeFromOyepaInternalOps(argPath_s):
    
    paths = []
    
    if type(argPath_s) == str: paths.append(argPath_s) # important, never extend() a list of str with a str argument (individual chars end being inserted, each as an item of its own)
    elif type(argPath_s) == list: paths.extend(argPath_s)
    else: assert False, "Invalid arg passed to removeFromOyepaInternalOps()"
    
    paths = [p.rstrip('/') for p in paths]
    
    lock_file = acquireInternalOpsFileLock() # this one needs an exclusive ("write") lock
    
    try: 
        
        internalOps = readInternalOps(mustGetLock=False)
        
        internalOps = list(set(internalOps).difference(paths)) # remove these paths from list (if present)
        
        oyepa_internal_ops_filepath = \
        os.path.join(user.home, cfg.oyepa_internal_ops_filename)
        
        with open(oyepa_internal_ops_filepath, "wb") as f:
            
            pickle.dump(internalOps, f)
            pass
        pass
    
    finally: release_lock(lock_file)
    
    return

# Waits until the filemon has ignored this internal operation
# or until we give up on waiting for it 
# (based on TIMEOUT_ON_WAITING_FOR_FILEMON). If it times out,
# this function runs removeFromInternalOps() on paths listed
# in its first arg. Always returns None

def waitOnInternalOpsCleared(argPath_s, previous_mtime):
    
    paths = []
    
    if type(argPath_s) == str: paths.append(argPath_s) # important, never extend() a list of str with a str argument (individual chars end being inserted, each as an item of its own)
    elif type(argPath_s) == list: paths.extend(argPath_s)
    else: assert False, "Invalid arg passed to waitOnInternalOpsCleared()"
    
    paths = [p.rstrip('/') for p in paths]
    
    while True:
        
        time.sleep(0.2)
        
        if len(set(readInternalOps()).intersection(paths)) == 0: 
            
            break
        
        if time.time() - previous_mtime >= cfg.TIMEOUT_ON_WAITING_FOR_FILEMON:
            print "wait on internal ops cleared TIMING OUT "
            removeFromOyepaInternalOps(argPath_s) # filemon doesn't seem to be reacting, "forget" about these paths ourselves
            break
        
        pass
    
    return


# NOTE: this function tests whether 'path' is in the list of
# paths currently being manipulated by the oyepa GUI. If
# the answer is positive, then *it removes that path from
# the internalOps list* and returns True. Otherwise, returns
# False.
#
# This function is invoked only by the filemon to find out whether
# or not it should ignore an operation it spots. It is for the
# changes performed by this function to the internalOps file
# that waitOnInternalOpsCleared looks.

def isInternalOyepaOp(path):
    
    path = path.rstrip('/')
    
    internalOps = readInternalOps()
    
    if path in internalOps:
        print "ignoring path %s, is internalOp"%path
        removeFromOyepaInternalOps(path)
        pass
    
    return path in internalOps


def copyDocTo(origPath, destPath):
    
    mtime = addToOyepaInternalOps([origPath, destPath]) # tell filemon not to interfere (in this case, not to prompt the user to tag the new copy of this doc)        
    
    errorMsg = None
    
    try: 
        
        if os.path.isdir(origPath): shutil.copytree(origPath, destPath)
        else: shutil.copyfile(origPath, destPath)
        pass
    
    except Exception, e: 
        
        errorMsg = "Copying this doc failed.\nException: " + str(e)
        
    finally: waitOnInternalOpsCleared([origPath, destPath], mtime)
    
    
    # since we have told the filemon not to interfere with our filesystem operations,
    # we must update the tags cache ourselves
    
    add_tags_in_path_to_cache(destPath)
    
    return errorMsg

def moveDocTo(origPath, destPath):
    
    mtime = addToOyepaInternalOps([origPath,destPath]) # tell filemon not to interfere
    
    errorMsg = None
    
    try: os.rename(origPath, destPath)
    
    except Exception, e: 
        
        errorMsg = "Moving this doc failed.\nException: " + str(e)
        
    finally: waitOnInternalOpsCleared([origPath, destPath], mtime)
    
    # since we have told the filemon not to interfere with our filesystem operations,
    # we must update the tags cache ourselves
    
    remove_tags_in_path_from_cache_and_filename_from_pending_updates(origPath)
    add_tags_in_path_to_cache(destPath)
    
    return errorMsg

def removeDoc(path):
    
    print "removeDoc(path=%s)"%path
    mtime = addToOyepaInternalOps(path) # tell filemon not to interfere
    
    errorMsg = None
    
    try: 
        
        if os.path.isdir(path): shutil.rmtree(path)
        else: os.unlink(path)
        pass
    
    except Exception, e: 
        
        errorMsg = "Removing this doc failed.\nException: " + str(e)
        
    finally:  waitOnInternalOpsCleared(path, mtime)
    
    # since we have told the filemon not to interfere with our filesystem operations,
    # we must update the tags cache ourselves
    
    remove_tags_in_path_from_cache_and_filename_from_pending_updates(path)
    
    return errorMsg


def add_tags_in_path_to_cache(path):
    
    doc_dir,filename = os.path.split(os.path.abspath(path.rstrip('/')))
    
    if doc_dir not in doc_dirs: return # we simply ignore paths to files outside of the doc repository
    
    tags = split_purename_and_tags_from_filename(filename, cfg.includeWordsInPurenameAsTags)[1]
    if tags != None: update_tag_cache(doc_dir, [], tags)
    return

def remove_tags_in_path_from_cache_and_filename_from_pending_updates(path):
    
    print "remove_tags_in_path_from_cache_and_filename_from_pending_updates"
    
    doc_dir,filename = os.path.split(os.path.abspath(path.rstrip('/')))
    
    if doc_dir not in doc_dirs: return # we simply ignore paths to files outside of the doc repository
    
    updates_dic = read_pending_updates(doc_dir)
    
    if filename in updates_dic:
        print "update pending for deleted path (%s->%s), will remove (i) tags embedded in update and (ii) update itself"%(path,updates_dic[filename])
        orig_filename = filename
        filename = updates_dic[filename]
        del updates_dic[orig_filename]
        write_pending_updates(doc_dir, updates_dic)
        pass
    
    origTags = split_purename_and_tags_from_filename(filename, cfg.includeWordsInPurenameAsTags)[1]
    if origTags != None: update_tag_cache(doc_dir, origTags, [])
    
    return

# MODULE TOP LEVEL CODE ########################################


doc_dirs = readDocDirList()


