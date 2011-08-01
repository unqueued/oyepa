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


import glob, os, re, sys, user

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from fslayer import validDocName
from generic_code import gui_excepthook, MyQRadioButton, runYesNoCheckBoxesDialog

import cfg

# Code ###################################################################

dateLineRegExp = re.compile(r"\d{1,2}\/\w+\/\d{4}$") # used to ignore the date line on top of each note (automatically added by the jed mode I use to type notes)


# Generates a 'numbered' filename based on a basename and (optionally)
# an extension which does not exist in dir d. Omitting the arg workdir 
# (or setting it to None) is equivalent to workdir=os.getcwd().
# 'ext' can be None/an empty string.

def generate_unused_numbered_filename(basename, ext, workdir=None):
    
    if workdir == None: workdir = os.getcwd()
    
    if ext != None and len(ext) > 0 and ext[0] != '.': ext = '.' + ext
    elif ext == None: ext = ''
    
    i = 2
    filename = basename + ext
    
    while os.path.exists(os.path.join(workdir,filename)):
        
        filename = basename + "(%d)"%i + ext
        i += 1
        pass
    
    return filename

def doEditAndMoveIntoNotesDir(filename):
    
    name, ext = os.path.splitext(filename)
    
    cmd = cfg.EDITOR_CMD_FOR_WNOTE + " "
    for c in filename: cmd += "\\" + c
    
    os.system(cmd)
    
    if not os.path.exists(filename): return False # user/editor did not create file
    
    newname = ""
    
    while True:
        
        newname, okPressed = QInputDialog.getText(None, "Name new note", \
        "Enter name for this note:")
        
        newname = str(newname.toLatin1()).strip()
        
        if not okPressed:
            print "ok NOT pressed"
            return False
        
        elif not validDocName(newname):
            
            QMessageBox.warning(None, "Name new note", \
            "Invalid name for a note")
            
        elif os.path.exists(os.path.join(cfg.NOTES_DIR_FOR_WNOTE, newname + ext)):
            
            QMessageBox.warning(None, "Name new note", \
            "Name already in use!")
            
        else: break
        pass
    
    newfilename = newname + ext
    
    if not os.path.exists(cfg.NOTES_DIR_FOR_WNOTE): os.mkdir(cfg.NOTES_DIR_FOR_WNOTE)
    
    try: os.rename(filename, os.path.join(cfg.NOTES_DIR_FOR_WNOTE,newfilename))
    
    except Exception,e:
        
        QMessageBox.error(None, "Name new note", \
        "Unable to move note into dir %s.\nError msg: %s"%(cfg.NOTES_DIR_FOR_WNOTE,str(e.toLatin1())))
        return False
    
    return True


def main():
    
    os.chdir(user.home)
    
    filename = cfg.UNTITLED_FILENAME_FOR_WNOTE
    
    name, ext = os.path.splitext(filename)
    
    existantUntitledNotes = []
    
    if os.path.exists(filename): existantUntitledNotes.append(filename)
    
    existantUntitledNotes.extend(glob.glob(name + "([0-9]*)" + ext))
    
    if len(existantUntitledNotes) > 0:
        
        retval = runYesNoCheckBoxesDialog("Found untitled notes. What do you want to do?", \
        ["Create new note", "Edit/tag untitled notes"], "Create new note")
        
        if retval == False: return
        
        if retval == "Create new note": filename = generate_unused_numbered_filename(name, ext)
        
        elif len(existantUntitledNotes) == 1: filename = existantUntitledNotes[0]
        
        else: # ask user to choose which of the several existant notes to edit
                                 
            def getFirstWords(filename):
                
                f = open(filename, "r")
                firstLine = "\n"
                while len(firstLine) == 1 or dateLineRegExp.match(firstLine): firstLine = f.readline()
                f.close()
                return firstLine.strip() if len(firstLine) > 1 else "[no text found!]"
            
            firstWordsOfEachNote = map(getFirstWords, existantUntitledNotes)
            
            retval = runYesNoCheckBoxesDialog("Which note should I open?", \
            firstWordsOfEachNote, firstWordsOfEachNote[0])
            
            if retval == False: return
            else: filename = existantUntitledNotes[firstWordsOfEachNote.index(retval)]
            pass
        
        pass
    
    
    doEditAndMoveIntoNotesDir(filename)
    return


app = QApplication(sys.argv)
sys.excepthook = gui_excepthook
main()
sys.exit(0)
