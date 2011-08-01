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

import os, mimetypes, pickle, re, subprocess, user, shutil

import cfg

GNOME = 1
KDE   = 2
OTHER_DESK_ENV = 3

class App:
    
    def __init__(self, name, cmd):
        
        self.name = name
        self.cmd = cmd
        return
    pass

# a provides a class that, for a given MIME type, provides
#
# (i) path to image file containing the correct icon
# (ii) name of apps that can are registered to open files of that mime type


class MimeMapper:
    
    def __init__(self): 
        
        self.ICON_DIR = os.path.abspath( os.path.join( os.path.dirname(__file__) , "icons") )
        
        # find out which desktop environment the user is running and import the module it provides to
        # find out which app to use for files of a certain mime type
        
        if os.getenv('GNOME_DESKTOP_SESSION_ID'): 
            
            global gnomevfs
            import gnomevfs
            
            self.DESK_ENV = GNOME
            
        elif os.getenv('KDE_FULL_SESSION'):

            global KMimeTypeTrader
            from PyKDE4.kdecore import KMimeTypeTrader
            
            self.DESK_ENV = KDE
            
        else: self.DESK_ENV = OTHER_DESK_ENV
        
        # setup (and read, if available) our caches of the mappings {extension -> mimetype} and 
        # {mimetype -> filepath of corresponding icon}. Especially the first of these caches really 
        # matters, since we spawn a process (xdg-mime) to learn about every unknown file extension...
        
        self.EXTENSION_TO_MIME_TYPE_CACHE = {} # maps extension (without leading dot) -> mime type string
        self.MIME_TYPE_TO_ICON_CACHE = {} # maps mime type string -> abs path of corresponding icon
        
        self.MIME_TYPES_CACHE_FILEPATH = cfg.MIME_TYPES_CACHE_FILEPATH

        if os.path.exists(self.MIME_TYPES_CACHE_FILEPATH):
            
            with open(self.MIME_TYPES_CACHE_FILEPATH) as f:
                self.EXTENSION_TO_MIME_TYPE_CACHE = pickle.load(f)
                self.MIME_TYPE_TO_ICON_CACHE      = pickle.load(f)
        
        return

    def __del__(self): # save our caches

        with open(self.MIME_TYPES_CACHE_FILEPATH, 'w') as f:
            pickle.dump(self.EXTENSION_TO_MIME_TYPE_CACHE, f)
            pickle.dump(self.MIME_TYPE_TO_ICON_CACHE     , f)

        return
    
    def _getMimeType(self, filename): # returns '' in case of failure
        
        # handle dirs
        
        if os.path.isdir(filename): return 'x-directory/normal' # this is what xdg-mime returns for dirs 
        
        # get the extension for this file and check if we already cached the mime type for this kind of file
        
        # [note! I don't just use os.path.splitext() because it guesses that everything after the last dot in a filename
        # is an extension. This screws up the handling of long, period-containing extensionless filenames.
        
        ext, mimeType = None, None
        
        if ']' in filename: # if this is a tagged filename, only consider dots AFTER the tags
            rightBracketPos = filename.index(']')
            dot = filename.rfind('.', rightBracketPos)
            if dot != -1: 
                ext = filename[dot+1:]
        else:
            ext = os.path.splitext(filename)[1] # ext is second value in pair (rest of path, .extension) returned by .splitext()
            
            if len(ext) > 1: ext = ext[1:] # AND we skip the dot (need to test, since splitext() will return empty string for extensionless files) [or just a dot for a weirdly named file 'file.']
            
            if len(ext) > 4: 
                ext = None # ignore suspiciously long "extensions" (jpeg, html are len 4 and commonly used)
        
        # if this got us an extension, look it up in our cache
        
        if ext:
            mimeType = self.EXTENSION_TO_MIME_TYPE_CACHE.get(ext, None)

        # if this didn't work, run xdg-mime to find out about it
        
        if mimeType is None:
            
            mimeType = subprocess.Popen('xdg-mime query filetype "%s"' % filename, shell=True, stdout=subprocess.PIPE).communicate()[0].strip()
            
            # if this worked (and this file has an extension), cache this mapping for future use

            if ext and mimeType:
                self.EXTENSION_TO_MIME_TYPE_CACHE[ext] = mimeType
        

        return mimeType
    
    
    def getIconPath(self, filename=None, mimeType=None): # call EITHER as getIcon(mimeType='text/plain') OR getIcon(filename='doc.txt'); must use keyword args; returns a path to a 'unknown file type' icon in case of trouble
        
        assert (filename or mimeType) and not (filename and mimeType)
        
        # figure out what info we were given
        
        if filename:
            mimeType = self._getMimeType( filename )
        
        iconPath = os.path.join(self.ICON_DIR, 'application-octet-stream.png')  # this is our default return value
        
        # see if we can improve on this default : )

        if mimeType: # necessary; if passed a filename, it is possible that _getMimeType() returned an empty string (if, eg, the file has been deleted/cannot be read)
                                    
            # try to find an icon path for this mime type in our cache
            
            iconPathFromCache = self.MIME_TYPE_TO_ICON_CACHE.get(mimeType, None)
            
            if iconPathFromCache:
                
                iconPath = iconPathFromCache
                
            else: # if that failed, look in the icon dir for a matching file name
                
                hyphenatedMimeType = re.sub('/','-', mimeType) # since filenames cannot contain slashes, on Linux icons for mime type text/plain are named 'text-plain.{EXTENSION}'
                
                possibleFilenames = [os.path.join(self.ICON_DIR, hyphenatedMimeType + '.png'), os.path.join(self.ICON_DIR, hyphenatedMimeType + '.svg')]
                
                existingFilenames = [fn for fn in possibleFilenames if os.path.exists(fn) ] # get a list of matching icon filepaths *that actually exist*
                
                if existingFilenames: 
                
                    iconPath = existingFilenames[0] 
        
                    # if we found something, cache this result
                    
                    self.MIME_TYPE_TO_ICON_CACHE[mimeType] = iconPath

                elif not mimeType.endswith('-x-generic'):
                
                    # if we still haven't got an icon, try to find a generic icon for the broad 'category' of this mime type
                    # (ASSUMING we aren't already looking at such a broad category...)
                    
                    broadMimeCategory = mimeType.split('/')[0] # gets us the 'audio' for 'audio/mp3', eg
                    iconPath = self.getIconPath(mimeType=broadMimeCategory + '-x-generic') # we love recursion
                pass
            
            pass
        
        return iconPath
    
    
    def getApps(self, filename): # returns a tuple (default app, [list of other apps]) that are registered as able to open this file; 'apps' in this context are App objects; in case of error, returns (None, [])
        
        defaultApp, otherApps = None, []
        
        mimeType = self._getMimeType(filename)
        
        if mimeType:
            
            if self.DESK_ENV == GNOME:
                
                # in the future [since gnomevfs is deprecated], this should be done using
                # import gio
                # gio.app_info_get_all_for_type(mimeType)                
                
                # both of these gnomevfs functions return tuples, where the element in [1] is the app name and [2] is the command to execute

                defaultAppInfo = gnomevfs.mime_get_default_application(mimeType)
                
                if defaultAppInfo: # if we got something 
                    
                    defaultApp = App(defaultAppInfo[1], defaultAppInfo[2])
                
                    otherApps = [App(app[1], app[2]) for app in gnomevfs.mime_get_all_applications(mimeType) ] 
                
            elif self.DESK_ENV == KDE:                
                
                kdeMimeTrader = KMimeTypeTrader.self()
                
                defaultAppInfo = kdeMimeTrader.preferredService(mimeType)
                
                if defaultAppInfo:
                    
                    defaultApp = App( unicode(defaultAppInfo.desktopEntryName()) , unicode(defaultAppInfo.exec_()) ) # unicode()s since funky PyQt "QString" strings are returned...
                
                    otherApps = [ App(unicode(s.desktopEntryName()), unicode(s.exec_()) ) for s in kdeMimeTrader.query(mimeType) ]
                
            else: # need to use our own file type -> app mapping...
                
                # XXX code from before
                
                pass
            
            otherApps = filter(lambda a: a.cmd != defaultApp.cmd, otherApps) # make sure we don't include the default app into the list of OTHER apps...
            pass
        
        for app in [defaultApp] + otherApps: # at least KDE sometimes stores the cmd to execute with a placeholder ('%U', '%f') at the end to indicate where the filename should go; we remove that
            
            if app.cmd.split()[-1].startswith('%'): app.cmd = ' '.join( app.cmd.split()[:-1] ) + ' '
            pass
        
        return defaultApp, otherApps
    
    
    def _generateOyepaIconCollection(self): # this function is only needs to be run when packaging oyepa (and even then, only if I have reason to believe the collection of items needs to be updated); it rebuilds our included set of icons.
        
        iconSourcesFile = open('ICON-SOURCES', 'w')
        
        if not os.path.exists(self.ICON_DIR): os.mkdir(self.ICON_DIR)

        os.chdir(self.ICON_DIR)
                
        collections = {} # will contain lists of icons belonging to different icon collections, eg {'oxygen': ['icon1.png', 'icon33.png'], 'crystalsvg': []}
        
        for coll in ['oxygen', 'Humanity', 'crystalsvg', 'Tangerine', 'gnome', 'hicolor']: collections[coll] = [] # initialize it with empty lists
        
        
        iconPaths = []
        
        # prioritize oxygen icons
        iconPaths += self._getResultsFromLocate("*icons*oxygen*mime*")
        favoriteColl = 'oxygen'
        
        # get list of all icons in the system (will include dupes for favoriteColl)
        
        iconPaths += self._getResultsFromLocate("*icons*mime*")
        
        for iconPath in iconPaths:
            
            if "/%d/" % cfg.ICON_SIZE in iconPath or "/%dx%d/" % (cfg.ICON_SIZE, cfg.ICON_SIZE) in iconPath.lower():
                
                if not os.path.isfile(iconPath): continue

                mimeType, extension = os.path.basename(iconPath).rsplit('.',1) # icons for a given mimetype are in a file named '/path/.../dir/mime-type.extension'
                
                # some tweaking is required 
                
                # 1) gnome provides some icons we might care to use, but they are prefixed with 'gnome-mime-'...
                
                if mimeType.startswith('gnome-mime-'): mimeType = mimeType[len('gnome-mime-'):]
                
                # 2) transform the name of oxygen's icon for directories into a name that will be used for all dirs. 
                #    xdg-mime reports for 'x-directory/normal' for dirs, so we use (the hyphenated version of) that.
                
                if mimeType == 'inode-directory': mimeType = 'x-directory-normal'
                
                # 3) use the Oxygen 'unknown' icon for all files for which we get the generic mime type 'application/octet-stream'

                if mimeType == 'unknown': mimeType = 'application-octet-stream' # again, remember to use an hyphen rather than a slash...
                
                if '-' not in mimeType: continue # only icons with composite names like 'application-msword' will ever be found by our code, so we ignore all those other system icons that don't contain an hyphen
                
                if ( os.path.exists(mimeType + ".png") or os.path.exists(mimeType + ".svg") ) and favoriteColl not in iconPath: # if this icon belongs to the favorite collection, we are not really 'skipping it': it simply means this is the second attempt to include it!
                    print 'skipping %s, already got one for that mime type' % iconPath
                    continue # already got one
                
                iconFilename = mimeType + '.' + extension
                
                shutil.copy(iconPath, iconFilename)
                
                for coll in collections:
                    if coll in iconPath: 
                        collections[coll].append(iconFilename)
                        break
                else:
                    print 'no collection matched ' + iconPath
                pass
            
            pass
        
        # record where we got each icon from in the license file
        
        iconSourcesFile.write('The set of icons included with oyepa is automatically generated from icons present on my Ubuntu system. See the file ICON-LICENSES for license information.\n\n')
        
        for coll in collections:
            
            if collections[coll]:
                iconSourcesFile.write("The following icons from the %s collection are included with oyepa:\n\n%s\n\n\n" % (coll, '\n'.join(collections[coll]) ) )

        iconSourcesFile.close()
        return
    
    
    def _getResultsFromLocate(self, query): # utility function, returns results of running 'locate' command
        
        locateResults = subprocess.Popen('locate "%s"' % query, shell=True, stdout=subprocess.PIPE).communicate()[0].split('\n')
        
        localResults = filter(lambda i: os.path.isfile(i), locateResults) # only files
        
        return locateResults
    
    pass
