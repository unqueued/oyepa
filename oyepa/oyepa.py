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

import datetime, os, sys, user, pickle, time, threading

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from fslayer import Doc, getDocDirs, getDocDirHierarchy, validTag, validDocName, getAllTags, runQuery, tagDoc, renameTag, removeTag,  getCurrentPureNameAndTagsForDoc, rebuildTagCache, split_purename_and_tags_from_filename, moveDocTo, removeDoc, copyDocTo
from generic_code import *

import cfg

import mime_info


mimeMapper = mime_info.MimeMapper()

# this is a list of threads. I use it to prevent segfaults due to threads being destroyed (due to 
# the thread var going out of scope (==> being garbage collected)  while the thread itself is still 
# running. Keeping around a global reference to the threads avoids this problem.

rememberTheThreads = []

# this is the function we use to start (and add/remove from the list above) threads

def runThread(threadArg):
    
    # first clean up our list of thread we want to prevent from being garbage collected
    # since they might still be running
    
    for t in rememberTheThreads[:]:
        if not t.isAlive(): rememberTheThreads.remove(t)
        pass
    
    # now execute the new thread, and append it to that list
    
    threadArg.start() # watch out! do not mistakenly (re)start iterator thread (see loop above)
    rememberTheThreads.append(threadArg)
    return

# if path is None, we simply execute cmd (without performing any '%' substition)
# if cfg.TERMINAL_HACK is True, the 'cmd' arg is ignored and we simply open a terminal
# window inside the dir-doc specifed in path

def run_cmd_on_path(cmd, path, usingTermHack=False):

    if not usingTermHack:
        
        words_in_cmd = cmd.split()
        
        if path != None:
            
            if "%" in words_in_cmd:
                
                words_in_cmd = map(lambda w: path if w == "%" else w , words_in_cmd)
                
            else: words_in_cmd.append(path)
            pass
        
        pid = os.spawnlp(os.P_NOWAIT, words_in_cmd[0], *words_in_cmd)
        
    else: # using cfg.TERMINAL_HACK
        
        cwd = os.getcwd()
        os.chdir(path)

        pid = os.spawnlp(os.P_NOWAIT, cfg.TERMINAL_APP, cfg.TERMINAL_APP) # spawnlp needs to be passed the program name twice

        os.chdir(cwd)

        pass
    
    class WaitOnPIDThread(threading.Thread): # create a thread which merely waitpid()s on the other process (necessary to avoid creating gazillions of defunct/zombie processes)
        
        def run(self): 
            try: os.waitpid(pid, 0)
            except: pass
            return
        pass
    
    runThread(WaitOnPIDThread())
    return

# return a (appName, cmd) pair which represent the default
# app/cmd to run on files of type 'extension'. In case of
# no such default app being defined, returns (None,None).
# When this extension is associated with the cfg.TERMINAL_HACK feature
# (which simply runs TERMINAL_APP inside a dir-doc), then
# we return (TERMINAL_HACK, None).

def getDefaultAppCmdForExt(extension):
    
    appMem = {}
    defaultAppForExtMem = {} # self.defaultAppForExtMem['txt'] = 'jed' (where 'jed' must be a key in self.appMem)
    
    if os.path.exists(cfg.APP_MEMORY_FILEPATH):
        
        with open(cfg.APP_MEMORY_FILEPATH, "rb") as f:
            
            # this file contains two pickle'd dictionaries; we extract both
            
            appMem = pickle.load(f)
            defaultAppForExtMem = pickle.load(f)
            pass
        pass
    
    if extension in defaultAppForExtMem:
        
        if defaultAppForExtMem[extension] in appMem: return (defaultAppForExtMem[extension], appMem[defaultAppForExtMem[extension]])
        
        elif defaultAppForExtMem[extension] == cfg.TERMINAL_HACK: return (cfg.TERMINAL_HACK, None)
        
        pass
    
    return (None,None)

class ThreadWithPleaseWaitMessage(threading.Thread):
    
    def __init__(self, msgBar): 
        threading.Thread.__init__(self)
        self.msgBar = msgBar
        return
    
    def execute(self):
        
        self.msgBar.setText("Please wait...")
        
        self.start()
        
        while self.isAlive():
            
            qApp.processEvents() # key!!
            
            time.sleep(0.1)
            pass
        self.msgBar.setText("")
        return
    
    pass



class RenameTagDialog(QDialog):
    
    def __init__(self, oldTag):
        
        QDialog.__init__(self)
        
        self.oldTag = oldTag
        
        self.setWindowTitle("Rename tag")        
        
        label = QLabel("New name for tag '%s':"%self.oldTag)
        self.lineedit = QLineEdit()
        compl = QCompleter(QStringList(list(getAllTags().difference([self.oldTag]))))
        self.lineedit.setCompleter(compl)
        
        label.setBuddy(self.lineedit)
        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(self.lineedit)
        buttonBox = QWidget()
        buttonLayout = QHBoxLayout()
        okButton = MyQPushButton("Ok")
        cancelButton = MyQPushButton("Cancel")
        okButton.setDefault(True)
        self.connect(okButton, SIGNAL("clicked()"), self.accept)
        self.connect(cancelButton, SIGNAL("clicked()"), self.reject)
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)
        buttonBox.setLayout(buttonLayout)
        
        layout.addWidget(buttonBox)
        self.setLayout(layout)
        
        return
    
    def getNewTagName(self):
        
        while True:
            
            if self.exec_() == QDialog.Rejected: return None
            
            newTag = unicode(self.lineedit.text().toUtf8(), 'utf-8').strip().lower()
            
            if not validTag(newTag): QMessageBox.warning(None, "Rename tag", "Invalid tag!")
            
            elif newTag == self.oldTag: QMessageBox.warning(None, "Rename tag", "That's the same tag you are trying to rename!")
            
            elif newTag in getAllTags():
                
                question = "A tag called '%s' already exists! Are you sure you want to merge '%s' with it?"%(newTag, self.oldTag)
                
                button = QMessageBox.question(self, "Warning (Rename Tag)", question, QMessageBox.Yes|QMessageBox.No, QMessageBox.No)
                
                if button == QMessageBox.Yes: break
                pass
            
            else: break
            pass
        
        return newTag
    
    pass

class GetCopyMoveDestinationDialog(QDialog):
    
    def __init__(self, item, winTitle, promptText, filenameWillBeText):
        
        QDialog.__init__(self)
        
        self.origDir = os.path.dirname(item.doc.path.rstrip('/'))
        
        self.docname = item.doc.docname # we use this when user decides to move doc into another doc-dir (in that case, we preserve tags)
        
        self.ext = item.doc.extension if item.doc.extension != cfg.FAKE_EXTENSION_FOR_DIRS else None
        
        self.basename = split_purename_and_tags_from_filename(item.doc.docname)[0]
        if len(self.basename) == 0: self.basename = "untitled"
        
        filename = self.basename
        if self.ext != None:  filename += '.' + self.ext
        
        self.winTitle = winTitle
        self.setWindowTitle(winTitle)
        label = QLabel(promptText)
        self.dirLineedit = QLineEdit(user.home)       
        
        self.completer = QCompleter(self)
        qdirModel = QDirModel(self.completer)
        qdirModel.setFilter(QDir.Dirs | QDir.NoDotAndDotDot)
        qdirModel.setSorting(QDir.IgnoreCase)
        self.completer.setModel(qdirModel)        
        self.dirLineedit.setCompleter(self.completer)
        
        label.setBuddy(self.dirLineedit)
        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(self.dirLineedit)
        
        self.filenameLabel = QLabel(filenameWillBeText+ " " + filename)
        layout.addWidget(self.filenameLabel)
        buttonBox = QWidget()
        buttonLayout = QHBoxLayout()
        okButton = MyQPushButton("Ok")
        cancelButton = MyQPushButton("Cancel")
        okButton.setDefault(True)
        self.connect(okButton, SIGNAL("clicked()"), self.accept)
        self.connect(cancelButton, SIGNAL("clicked()"), self.reject)
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)
        buttonBox.setLayout(buttonLayout)
        
        layout.addWidget(buttonBox)
        self.setLayout(layout)
        return
    
    def getDestinationPath(self):
        
        while True:
            
            if self.exec_() == QDialog.Rejected: return None
            
            dirname = unicode(self.dirLineedit.text().toUtf8(), 'utf-8').strip()
            dirname = os.path.abspath(dirname)
            
            if not os.path.isdir(dirname): QMessageBox.warning(None, self.winTitle, "Invalid dir name!")
            elif self.origDir == dirname: QMessageBox.warning(None, self.winTitle, "This doc is already stored in %s!"%self.origDir)
            else: break
            pass
        
        if dirname in getDocDirs(): # special case in which we are moving a doc from one doc dir into another one. In this situation, we want to preserve the tags in the filename (however, we don't go the extra mile to actually check if there is a NEWER filename for this file availabe in the .updates file and use that instead...)
            
            filename = self.docname
            
            if self.ext != None: filename += '.' + self.ext
            
            destPath = os.path.join(dirname, filename)
            
            if os.path.exists(destPath): 
                
                # this check is important for the case when os.path.abspath(dirname)
                # is one of the doc_dirs
                
                QMessageBox.warning(None, self.winTitle, "Error: a document already exists in that doc dir with this exact same name and tags\nPath: %s"%destPath)
                print "getDestPath() == None"
                return None
            
            pass
        
        else: 
            
            destPath = os.path.join(dirname, \
            generate_unused_numbered_filename(self.basename, self.ext, dirname))
            
            pass
        
        print "getDestPath() == " + unicode(destPath, 'utf-8')
        return destPath
    
    pass



class AppCmdDialog(QDialog):
    
    def updateOkButton(self): # this function controls whether or not the 'ok' button is grayed out. The user can only click 'ok' if either a command has been entered (and optionally an app name, but if so it must not collide with the reserved name cfg.TERMINAL_HACK) or this doc is a dir and she chose cfg.TERMINAL_HACK as the app (to invoke the 'open xterm in dir-doc' hack)
        
        self.okButton.setEnabled( \
        (self.isdir and self.getAppName() == cfg.TERMINAL_HACK and len(self.getCmd()) == 0) or \
        ( self.getAppName() != cfg.TERMINAL_HACK and len(self.getCmd()) > 0 ) )
        
        return
    
    def updateForgetButton(self, text): # this function grays out the "forget" button depending on whether or not the user has entered a valid app name into that lineedit
        
        self.forgetButton.setEnabled(unicode(text.toUtf8(),'utf-8') in self.appMem)
        return
    
    def __init__(self, extension, isdir, parent):
        
        QDialog.__init__(self, parent)
        
        self.setWindowTitle("Open doc with...")
        
        self.isdir = isdir
        
        self.extension = extension
        
        self.appMem = {} # eg, self.appMem['jed'] = 'xterm -e jed'
        self.defaultAppForExtMem = {} # eg, self.defaultAppForExtMem['txt'] = 'jed' (where 'jed' must be a key in self.appMem)
        
        if os.path.exists(cfg.APP_MEMORY_FILEPATH):
            
            with open(cfg.APP_MEMORY_FILEPATH, "rb") as f:
                
                self.appMem = pickle.load(f)
                self.defaultAppForExtMem = pickle.load(f)
                pass
            pass
        
        dialLayout = QVBoxLayout()
        self.cmdLineEdit = QLineEdit()
        self.appNameLineEdit = QLineEdit()
        
        prompt = "File/dir type: " + (extension if extension != None else "[doc name lacks an extension]")
        
        prompt += "\nDefault app: "
        if extension in self.defaultAppForExtMem: prompt += self.defaultAppForExtMem[extension]
        else: prompt += "(none set)"
        
        prompt += "\n"
        
        if self.isdir: prompt += "[This doc is a directory, type '%s' as the app name (leaving\nthe 'command' line empty) to open a terminal inside that dir.]\n"%cfg.TERMINAL_HACK
        
        self.completions = self.appMem.keys()
        
        if self.isdir and cfg.TERMINAL_HACK not in self.completions: 
            
            self.completions.append(cfg.TERMINAL_HACK)
            pass
        
        self.compl = QCompleter(QStringList(self.completions))
        self.appNameLineEdit.setCompleter(self.compl)
        
        self.connect(self.appNameLineEdit, SIGNAL("textChanged(QString)"), \
        self.updateCmdLineEdit)
        
        self.connect(self.appNameLineEdit, SIGNAL("textChanged(QString)"), \
        self.updateForgetButton)
        
        self.connect(self.appNameLineEdit, SIGNAL("textChanged(QString)"), self.updateOkButton)
        self.connect(self.cmdLineEdit, SIGNAL("textChanged(QString)"), self.updateOkButton)
        
        appNameLabel = QLabel(prompt + "\n&App name:")
        appNameLabel.setBuddy(self.appNameLineEdit)
        dialLayout.addWidget(appNameLabel)
        dialLayout.addWidget(self.appNameLineEdit)
        
        cmdLabel = QLabel("&Command:")
        cmdLabel.setBuddy(self.cmdLineEdit)
        dialLayout.addWidget(cmdLabel)
        dialLayout.addWidget(self.cmdLineEdit)
        
        buttonBox = QWidget()
        buttonLayout = QHBoxLayout()
        self.okButton = MyQPushButton("Ok")
        cancelButton = MyQPushButton("Cancel")
        self.forgetButton = MyQPushButton("&Forget app")
        self.makeDefaultAppButton = MyQCheckBox("Make this the &default app for this document type")
        self.makeDefaultAppButton.setCheckState(Qt.Checked if (extension != None and extension not in self.defaultAppForExtMem) else Qt.Unchecked) # we do not remember a default app to open extensionless files, so let us not check this box to begin with
        self.makeDefaultAppButton.setEnabled(extension != None) # we refuse to remember a default app for extensionless files...
        
        self.okButton.setDefault(True)
        self.okButton.setEnabled(False)
        self.forgetButton.setEnabled(False)
        self.connect(self.okButton, SIGNAL("clicked()"), self.accept)
        self.connect(cancelButton, SIGNAL("clicked()"), self.reject)
        self.connect(self.forgetButton, SIGNAL("clicked()"), self.delAppFromMem)
        buttonLayout.addWidget(self.okButton)
        buttonLayout.addWidget(cancelButton)
        buttonLayout.addWidget(self.forgetButton)
        buttonLayout.addWidget(self.makeDefaultAppButton)
        buttonBox.setLayout(buttonLayout)
        
        dialLayout.addWidget(buttonBox)
        
        self.setLayout(dialLayout)
        return
    
    def delAppFromMem(self):
        
        appName = self.getAppName()
        
        if appName in self.appMem:
            
            question = "Forget about app '%s'?"%appName
            
            button = QMessageBox.question(self, "oyepa", question, QMessageBox.Yes|QMessageBox.No)
            
            if button == QMessageBox.Yes:
                
                del self.appMem[appName]
                
                for (ext, defaultApp) in self.defaultAppForExtMem.copy().items():
                    
                    if appName == defaultApp: del self.defaultAppForExtMem[ext]
                    pass
                
                self.appNameLineEdit.clear()
                self.cmdLineEdit.clear()
                
                self.completions.remove(appName) 
                self.compl = QCompleter(QStringList(self.completions)) 
                self.appNameLineEdit.setCompleter(self.compl) # some versions of Qt 4.x crash when switching QCompleters
                
                self.forgetButton.setEnabled(False)
                pass
            
            pass
        
        self.appNameLineEdit.setFocus()
        return
    
    def exec_(self):
        
        retval = QDialog.exec_(self)
        
        cmd = self.getCmd()
        appName = self.getAppName()
        
        # first, handle the case in which we are opening a dir using our cfg.TERMINAL_HACK hack
        # and want to make that the default action for this type of dir
        
        if appName == cfg.TERMINAL_HACK and len(cmd) == 0 and self.isdir and \
        self.makeDefaultAppButton.checkState() == Qt.Checked: 
            
            self.defaultAppForExtMem[self.extension] = cfg.TERMINAL_HACK
            
        elif len(cmd) > 0 and len(appName) > 0: # now handle the general case (user entered an app name and the corresponding command)
            
            if appName == cfg.TERMINAL_HACK: # we cannot allow the user to define an app with a name which coincides with cfg.TERMINAL_HACK
                
                QMessageBox.warning(None, "oyepa", "That app name ('%s') is reserved for a built-in hack!\nYou cannot redefine the associated command."%cfg.TERMINAL_HACK)
                return QDialog.Rejected
            
            elif appName not in self.appMem.keys():
                
                self.appMem[appName] = cmd
                
            elif cmd != self.appMem[appName]: 
                
                question = "Modify the command for app '%s' from\n%s\nto\n%s\n?"%(appName, self.appMem[appName], cmd)
                
                button = QMessageBox.question(self, "oyepa", question, QMessageBox.Yes|QMessageBox.No)
                
                if button == QMessageBox.Yes:
                    
                    self.appMem[appName] = cmd
                    pass
                pass
            
            if self.makeDefaultAppButton.checkState() == Qt.Checked: self.defaultAppForExtMem[self.extension] = appName
            pass
        
        with open(cfg.APP_MEMORY_FILEPATH, "wb") as f:
            
            pickle.dump(self.appMem, f)
            pickle.dump(self.defaultAppForExtMem, f)
            pass
        
        return retval
    
    
    def updateCmdLineEdit(self, text):
        
        if unicode(text.toUtf8(), 'utf-8') in self.appMem.keys():
            
            self.cmdLineEdit.setText(self.appMem[unicode(text.toUtf8(), 'utf-8')])
        else: self.cmdLineEdit.setText("")
        
        return
    
    def getCmd(self): return unicode(self.cmdLineEdit.text().toUtf8(), 'utf-8').strip()
    def getAppName(self): return unicode(self.appNameLineEdit.text().toUtf8(), 'utf-8').strip().lower()
    
    pass


class DirSelector(QTreeWidget):
    
    def __init__(self, doc_dir_hierarchy, dirsInCmdLine, parent = None):
        
        QTreeWidget.__init__(self,parent)
        bubu = QItemSelectionModel(QStandardItemModel())
        #self.setSelectionModel(QItemSelectionModel.ToggleCurrent)
        self.selectedDirs = set()
        
        if('HierarchyRootElements' in doc_dir_hierarchy):
            hierarchyStack = []
            stringIndex = 0;
            treeItemIndex = 1;
            childElementsIndex = 2;
            lastElementIndex = -1;
            
            # Hier muss ich noch eine for-Schleife ueber alle Root-Elemente drum rum machen und das
            # .pop hinter dem doc_dir_hierarchy['HierarchyRootElements'] wegmachen.
            rootElements = doc_dir_hierarchy['HierarchyRootElements']
            childElements = rootElements
            while True:
                while( len(childElements) > 0 ):
                    childString = childElements.pop();
                    childTreeItem = QTreeWidgetItem(QStringList(os.path.basename(childString)))
                    childTreeItem.setData(Qt.UserRole,0,QVariant(QString(childString)))
                    
                    if( len(hierarchyStack) == 0 ):
                        self.addTopLevelItem(childTreeItem)
                    else:
                        hierarchyStack[lastElementIndex][treeItemIndex].addChild(childTreeItem)
                                   
                    if( childString in doc_dir_hierarchy ):
                        stackElement = []
                        stackElement.insert(stringIndex,childString)
                        stackElement.insert(treeItemIndex, childTreeItem)
                        stackElement.insert(childElementsIndex, childElements)   
                        hierarchyStack.append(stackElement)
                        
                        childElements = doc_dir_hierarchy[childString]
                if( len(hierarchyStack) - 1 == 0 ):
                    break    
                else:
                    stackElement = hierarchyStack.pop()
                    childElements = stackElement[childElementsIndex]

        self.connect(self, SIGNAL("itemClicked(QTreeWidgetItem*, int)"), self.updateSelectedSingleDir)
        self.connect(self, SIGNAL("itemDoubleClicked(QTreeWidgetItem*, int)"), self.updateSelectedDirTree)
                        
        return
    
    def updateSelectedSingleDir(self, TreeWidgetItem, col):
        
        #dirName = unicode(TreeWidgetItem.property("abspath").toString().toUtf8(), 'utf-8')
        print "updateSelectedSingleDir reached"
        dirName = TreeWidgetItem.data(Qt.UserRole,0)
        if TreeWidgetItem.isSelected() == True:
            self.setItemSelected(TreeWidgetItem,False)
            self.selectedDirs.add(dirName)
            
        else: 
            self.selectedDirs.remove(dirName)
            self.setItemSelected(TreeWidgetItem,True)
        
        #self.emit(SIGNAL("selectedDirsChanged()"))
        return
    
    def updateSelectedDirTree(self, QTreeWidgetItem, col):
        pass
    
    def getSelectedDirs(self): return self.selectedDirs
    
    pass

#class DirSelector(QGroupBox):
#    
#    def __init__(self, doc_dirs, dirsInCmdLine, parent = None):
#        
#        QGroupBox.__init__(self, "Search &in...", parent)
#        
#        self.buttonGroup = QButtonGroup(self)
#        self.buttonGroup.setExclusive(False)
#        
#        layout = QVBoxLayout()
#        
#        self.selectedDirs = set()
#        
#        # now setup the checkboxes
#        
#        dirsInCmdLine = map(os.path.abspath, dirsInCmdLine)
#        
#        
#        for d in sorted(doc_dirs, key=os.path.basename):
#            
#            cbox = QCheckBox(os.path.basename(d))
#            cbox.setProperty("abspath", QVariant(QString(d)))
#            
#            if len(dirsInCmdLine) == 0 or d in dirsInCmdLine:
#                
#                cbox.setCheckState(Qt.Checked)
#                self.selectedDirs.add(d)
#                
#            else: cbox.setCheckState(Qt.Unchecked)
#            
#            self.buttonGroup.addButton(cbox)
#            layout.addWidget(cbox)
#            pass
#        
#        self.connect(self.buttonGroup, SIGNAL("buttonClicked(QAbstractButton*)"), self.updateSelectedDirs)
#        layout.addStretch(1)
#        self.setLayout(layout)
#        return
#    
#    def updateSelectedDirs(self, cbox):
#        
#        dirName = unicode(cbox.property("abspath").toString().toUtf8(), 'utf-8')
#        
#        if cbox.checkState() == Qt.Checked:
#            
#            self.selectedDirs.add(dirName)
#            
#        else: self.selectedDirs.remove(dirName)
#        
#        self.emit(SIGNAL("selectedDirsChanged()"))
#        return
#    
#    def getSelectedDirs(self): return self.selectedDirs
#    
#    pass

class MusicExtensionsWidget(QGroupBox):
    
    def __init__(self, parent = None):
        
        QGroupBox.__init__(self, "Album or radio?", parent)
        
        self.buttonGroup = QButtonGroup(self)
        self.buttonGroup.setExclusive(True)
        
        layout = QVBoxLayout()
        radio = QRadioButton("Internet radio")
        albums = QRadioButton("Albums")
        albums.setChecked(Qt.Checked)
        self.currentChoice = cfg.FAKE_EXTENSION_FOR_DIRS
        
        self.buttonGroup.addButton(radio)
        self.buttonGroup.addButton(albums)
        layout.addWidget(radio)
        layout.addWidget(albums)
        self.setLayout(layout)
        
        
        self.connect(self.buttonGroup, SIGNAL("buttonClicked(QAbstractButton*)"), self.updateCurrentChoice)
        
        return
    
    def updateCurrentChoice(self, cbox): 
        
        if cbox.text() == "Internet radio": self.currentChoice = "radio"
        else: self.currentChoice = cfg.FAKE_EXTENSION_FOR_DIRS
        
        self.emit(SIGNAL("extensionListChanged()"))
        print "currentChoice: " + unicode(self.currentChoice, 'utf-8')
        return
    
    def getExtensions(self): return [self.currentChoice] # IMPORTANT! If we just return a string "radio", then the caller will get a list ["r","a","d","i","o"]
    
    pass


class DefaultExtensionsWidget(QWidget):
    
    def __init__(self, parent = None):
        
        QWidget.__init__(self,parent)
        
        layout = QVBoxLayout()
        
        label = QLabel("File e&xtensions (eg, enter 'html pdf' to only list HTML and PDF files):")
        
        self.lineedit = ExtensionsLineEdit(self)
        
        label.setBuddy(self.lineedit)
        # the rest of the code expects US (ie, NOT the self.lineedit) to emit this signal when the list of admissible extensions changes
        
        self.connect(self.lineedit, SIGNAL("extensionListChanged()"), self.emitExtensionsChanged)
        
        layout.addWidget(label)
        layout.addWidget(self.lineedit)
        self.setLayout(layout)
        return
    
    def emitExtensionsChanged(self): self.emit(SIGNAL("extensionListChanged()"))
    
    def getExtensions(self):
        
        return unicode(self.lineedit.text().toUtf8(), 'utf-8').strip().lower().split()
    pass


class ExtensionsLineEdit(QLineEdit):
    
    def __init__(self, parent):
        
        QLineEdit.__init__(self, parent)
        self.previousText = None        
        return
    
    def keyPressEvent(self, event):
        
        if event.key() == Qt.Key_Return: self.checkForChanges()
        
        QLineEdit.keyPressEvent(self, event)
        
        return
    
    def focusOutEvent(self, event):
        
        self.checkForChanges()
        QLineEdit.focusOutEvent(self, event)
        return
    
    def checkForChanges(self):
        
        if self.previousText != unicode(self.text().toUtf8(), 'utf-8').strip().lower():
            
            self.emit(SIGNAL("extensionListChanged()"))
            self.previousText = unicode(self.text().toUtf8(), 'utf-8').strip().lower()
            pass
        
        return
    
    pass

class SelectedTagsQListWidget(NicerQListWidget):
    
    def __init__(self, widgetToPassFocusToIfEmpty, preselectedTags, parent = None):
        
        NicerQListWidget.__init__(self, parent)
        
        self.widgetToPassFocusToIfEmpty = widgetToPassFocusToIfEmpty
        
        self.addMenuAction("&Deselect tag",  self.deselectTag)
        
        self.connect(self, SIGNAL("itemActivated(QListWidgetItem*)"), self.deselectTag)
        
        # populate this QListWidget with the tags already defined for the doc 
        # we are tagging, if any
        
        for tag in preselectedTags: self.addItem(tag)
        
        self.setEnabled(self.count() > 0)
        
        return
    
    def keyPressEvent(self, event):
        
        item = self.currentItem()
        
        if  item != None and event.key() in (Qt.Key_Delete, Qt.Key_D):
            self.deselectTag()
            pass
        
        NicerQListWidget.keyPressEvent(self, event)
        return
    
    def deselectDeletedTags(self):
        
        allTags = getAllTags()
        currentlySelectedTags = self.getItems()
        
        # QListWidget.takeItem(row) is tricky to use for multiple item removals.
        # I just clear all items and add back in those which should be kept around.
        
        tagsToKeep = filter(lambda t: t in allTags, currentlySelectedTags)
        
        self.clear()
        
        self.addItems(tagsToKeep)
        
        return
    
    def deselectTag(self):
        
        item = self.currentItem()
        if item == None: return
        
        tag = unicode(item.text().toUtf8(), 'utf-8')
        
        self.takeItem(self.row(item))
        self.emit(SIGNAL("tagDeselected(QString)"), QString(tag))
        
        if self.count() == 0: 
            
            self.setEnabled(False)
            self.widgetToPassFocusToIfEmpty.setFocus()
            pass
        
        return  
    
    pass

class MyQLineEdit(QLineEdit):
    
    def passFocusTo(self, widget):
        
        self.completionsListView = widget
        return
    
    def keyPressEvent(self, event):
        
        if event.key() == Qt.Key_Down and \
        (self.completionsListView.count() > 1 or \
        self.completionsListView.item(0).text() != cfg.NO_SUGGESTIONS_ITEM_STR):
            
            self.completionsListView.setFocus()
            pass
        
        QLineEdit.keyPressEvent(self,event)
        return
    
    pass

class CompletionsQListWidget(NicerQListWidget):
    
    def __init__(self, tagSelector, preselectedTags, tagLineEdit, selectedListView, parent = None):
        
        NicerQListWidget.__init__(self, parent)
        
        self.tagSelector = tagSelector
        
        self.tagLineEdit = tagLineEdit
        self.selectedListView = selectedListView
        
        self.addMenuAction("&Delete tag",  self.tagSelector.doDeleteTagDialog)
        self.addMenuAction("&Rename tag", self.tagSelector.doRenameTagDialog)
        
        self.connect(self, SIGNAL("itemActivated(QListWidgetItem*)"), self.selectTag)
        
        # populate this QListWidget with all presently defined tags
        
        allNotCurrentlySelectedTags = \
        filter(lambda t: t not in preselectedTags, getAllTags())
        
        allNotCurrentlySelectedTags.sort()
        
        for tag in allNotCurrentlySelectedTags: self.addItem(tag)
        
        if len(allNotCurrentlySelectedTags) == 0:
            
            i = QListWidgetItem(cfg.NO_SUGGESTIONS_ITEM_STR)
            i.setFlags(Qt.ItemFlags())
            self.addItem(i)
            pass
        
        self.setEnabled(len(allNotCurrentlySelectedTags) > 0)
        
        return
    
    def selectTag(self, item):
        
        tag = unicode(item.text().toUtf8(), 'utf-8')
        self.setCurrentItem(None) # at least here this works, while clearSelection() doesn't
        self.tagLineEdit.setText(tag)
        self.tagLineEdit.setFocus()
        self.tagLineEdit.emit(SIGNAL("returnPressed()"))
        return
    
    
    def updateCompletions(self):
        
        partialTag = unicode(self.tagLineEdit.text().toUtf8(), 'utf-8').strip().lower()
        selectedTags = self.selectedListView.getItems()
        
        matchingTags = \
        filter(lambda t: partialTag in t and \
        t not in selectedTags, getAllTags())
        
        matchingTags.sort()
        
        self.clear()
        
        if len(matchingTags) > 0: self.addItems(matchingTags)
        
        else:
            
            i = QListWidgetItem(cfg.NO_SUGGESTIONS_ITEM_STR)
            i.setFlags(Qt.ItemFlags())
            self.addItem(i)
            pass
        
        self.setEnabled(len(matchingTags) > 0)
        return
    
    def keyPressEvent(self, event):
        
        row = self.currentRow()
        
        if row != -1 and event.key() == Qt.Key_Return:
            
            self.selectTag(self.currentItem())
            pass
        
        elif row in (0,-1) and event.key() == Qt.Key_Up:
            
            self.tagLineEdit.setFocus()
            pass
        
        elif row != -1 and event.key() == Qt.Key_R:
            
            self.tagSelector.doRenameTagDialog()
            
        elif row != -1 and event.key() == Qt.Key_D:
            
            self.tagSelector.doDeleteTagDialog()
            pass
        
        QListWidget.keyPressEvent(self, event)
        return
    
    pass



class TagSelector(QWidget):
    
    
    def __init__(self, prompt, msgBar, preselectedTags, parent = None):
        
        QWidget.__init__(self, parent)
        
        entryBox = QWidget()
        entryBoxLayout = QHBoxLayout()
        
        self.msgBar = msgBar
        
        promptLabel = QLabel(prompt)
        self.tagLineEdit = MyQLineEdit()
        promptLabel.setBuddy(self.tagLineEdit)
        
        entryBoxLayout.addWidget(promptLabel)
        entryBoxLayout.addWidget(self.tagLineEdit)
        entryBox.setLayout(entryBoxLayout)
        
        selectedLabel = QLabel("Selected &tags:")
        self.selectedListView = SelectedTagsQListWidget(self.tagLineEdit, preselectedTags)
        
        selectedLabel.setBuddy(self.selectedListView)
        
        self.completionsLabel = QLabel("Possible completions:")
        self.completionsListView = CompletionsQListWidget(self, preselectedTags, self.tagLineEdit, self.selectedListView)
        
        self.tagLineEdit.passFocusTo(self.completionsListView) # ugly hack
        
        leftBox = QWidget()
        rightBox = QWidget()
        
        leftBoxLayout = QVBoxLayout()
        rightBoxLayout = QVBoxLayout()
        
        leftBoxLayout.addWidget(entryBox)
        leftBoxLayout.addWidget(self.completionsLabel)
        leftBoxLayout.addWidget(self.completionsListView)
        leftBox.setLayout(leftBoxLayout)
        
        rightBoxLayout.addWidget(selectedLabel)
        rightBoxLayout.addWidget(self.selectedListView)
        rightBox.setLayout(rightBoxLayout)
        mainLayout = QHBoxLayout()
        mainLayout.addWidget(leftBox)
        mainLayout.addWidget(rightBox)
        self.setLayout(mainLayout)
        
        # since a this widget glues together a subwidgets, we need to listen
        # to the signals they emit and finish up the work they start
        
        # first, we need to know when the user has manually entered a tag and
        # pressed Enter (or selected one of the suggested completions from the
        # completionsListView; these are equivalent*).
        # [(*) When a completion is selected, the completionsListView places it 
        # into the tagLineEdit and gets the latter to emit its "returnPressed()"
        # signal. So we only need to listen to this signal.]
        
        self.connect(\
        self.tagLineEdit, SIGNAL("returnPressed()"), self.selectEnteredTag)
        
        # second, we need to know when a tag has been deselected in the
        # selectedListView.
        
        self.connect(\
        self.selectedListView, SIGNAL("tagDeselected(QString)"), \
        self.tagDeselected)
        
        # third, the completionsListView needs to update itself whenever
        # the text in the tagLineEdit changes.
        
        self.connect(self.tagLineEdit, SIGNAL("textChanged(QString)"), \
        self.completionsListView.updateCompletions)
        
        return
    
    # this is called by the MatchingDocs widget after it 
    # performs an operation which might have changed the
    # set of all defined tags. We (TagSelector) reciprocate
    # by letting the MatchingDocs widget know whenever we
    # undefine a tag (by either deleting or renaming it),
    # so that it can update the tags listed in the doc
    # descriptions it is showing.
    
    def updateAfterChangesToSetOfAllTags(self):
        
        print "tagSelector.updateAfterChangesToSetOfAllTags()"
        
        self.selectedListView.deselectDeletedTags()
        self.completionsListView.updateCompletions()
        return
    
    def doRenameTagDialog(self):
        
        item = self.completionsListView.currentItem()
        
        if item == None: return
        
        oldTag = unicode(item.text().toUtf8(), 'utf-8').strip().lower()
        
        if oldTag == None or len(oldTag) == 0: return
        
        renameTagDialog = RenameTagDialog(oldTag)
        
        newTag = renameTagDialog.getNewTagName()
        
        if newTag != None: self.renameTag(oldTag, newTag)
        
        return
    
    def doDeleteTagDialog(self):
        
        item = self.completionsListView.currentItem()
        
        if item == None: return
        
        tag = unicode(item.text().toUtf8(), 'utf-8').strip().lower()
        
        question = "Are you SURE you want to remove the tag '%s' from all documents?"%tag
        
        button = QMessageBox.question(self, "Warning", question, QMessageBox.Yes|QMessageBox.No, QMessageBox.No)
        
        if button == QMessageBox.Yes: self.renameTag(tag, None)
        
        return
    
    def renameTag(self, oldTag, newTag):
        
        class RenamerThread(ThreadWithPleaseWaitMessage):
            
            def run(self): self.retval = renameTag(oldTag, newTag)
            pass
        
        self.renamerThread = RenamerThread(self.msgBar)
        self.renamerThread.execute() # blocks until rename operation (in fslayer) is over
        
        if type(self.renamerThread.retval) == str: 
            
            QMessageBox.warning(None, "Error", "Unable to conclude %s operation. Error msg:\n%s"%("renameTag" if newTag != None else "removeTag", self.renamerThread.retval))
            return
        
        # if we get here the tag rename operation was successful
        
        # before proceeding, we need to check whether oldTag was currently selected, newTag wasn't and this 
        # is a rename operation. If that is the case, then we need to ensure that 'newTag' is put in oldTag's 
        # place in the selectedListView. 
        
        if oldTag in self.getSelectedTags() and newTag != None and newTag not in self.getSelectedTags():
            
            
            for i in range(self.selectedListView.count()):
                
                item = self.selectedListView.item(i)
                if unicode(item.text().toUtf8(), 'utf-8').lower().strip() == oldTag: item.setText(newTag)
                pass
            pass
        
        self.updateAfterChangesToSetOfAllTags() # this will make completionsListView and selectedListView (for _removal_ of oldTag) update themselves
        
        print "TagSelector.renameTag() emitting 'setOfAllTagsChanged()'"
        self.emit(SIGNAL("setOfAllTagsChanged()")) # ... and let MatchingDocs know about it
        return
    
    def getSelectedTags(self): return self.selectedListView.getItems()
    
    def selectEnteredTag(self):
        
        tag = unicode(self.tagLineEdit.text().toUtf8(), 'utf-8').strip().lower()
        self.tagLineEdit.clear()
        
        if not validTag(tag):
            
            QMessageBox.warning(None, "oyepa", "Invalid tag!" if len(tag) > 0 else "Empty tag!")
            return False
        
        elif tag in self.getSelectedTags():
            
            QMessageBox.warning(None, "oyepa", "That tag is a dupe!")
            return False
        
        # add it to the selectedListView widget
        
        self.selectedListView.addItem(tag)
        
        self.selectedListView.setEnabled(True)
        
        # now just ensure we do not keep suggesting it as a possible completion
        
        self.completionsListView.updateCompletions()
        
        # and let others know that an additional tag has been selected (most notably, this signal is linked to runQuerySlot() in do_search())
        
        self.emit(SIGNAL("tagSelected(QString)"), QString(tag))
        return
    
    def tagDeselected(self, tag):
        
        tag = unicode(tag.toUtf8(), 'utf-8')
        
        self.completionsListView.updateCompletions()
        
        # now we must reemit the signal this same function is bound to, since the
        # main code "listens" for signals coming from TagSelector (rather than its subwidgets)
        
        self.emit(SIGNAL("tagDeselected(QString)"), QString(tag))
        return
    
    pass

class DocNameWidget(QWidget):
    
    def __init__(self, docName, parent = None):
        
        QWidget.__init__(self, parent)
        
        layout = QHBoxLayout();
        
        nameLabel = QLabel("DoC name:")
        
        self.nameLineEdit = QLineEdit(docName)
        self.nameLineEdit.setEnabled(False)
        self.shortcut = QShortcut(QKeySequence("Alt+C"), self)
        
        self.connect(self.shortcut, SIGNAL("activated()"), self.switchToLineEdit)
        
        layout.addWidget(nameLabel)
        layout.addWidget(self.nameLineEdit)
        self.setLayout(layout)
        
        self.connect(self.nameLineEdit, SIGNAL("editingFinished()"), self.validateDocName)
        return
    
    def getDocName(self): return unicode(self.nameLineEdit.text().toUtf8(), 'utf-8').strip()
    
    def switchToLineEdit(self):
        
        self.nameLineEdit.setEnabled(True)
        self.nameLineEdit.setFocus()
        return
    
    def validateDocName(self):
        
        if QApplication.activeWindow() == None: return
        
        docName = self.getDocName()
        
        if not validDocName(docName):
            
            QMessageBox.warning(None, "oyepa", "Invalid docname!" if len(docName) > 0 else "Empty docname!")
            self.nameLineEdit.clear()
            self.nameLineEdit.setFocus()
            self.emit(SIGNAL("badDocName()"))
            
        else: 
            
            self.emit(SIGNAL("goodDocName()"))
            self.nameLineEdit.setEnabled(False)
            self.clearFocus()
            pass
        
        return
    
    pass

class DocListWidgetItem(QTableWidgetItem):
    
    def __init__(self, doc, itemType):
        
        assert itemType in ("ICON_AND_NAME", "DATE", "TIMESTAMP")
        
        if itemType == "ICON_AND_NAME":
            
            iconFilepath = mimeMapper.getIconPath(doc.path)
            
            QTableWidgetItem.__init__(self, QIcon(iconFilepath), doc.docname)
            
        elif itemType == "DATE":
            
            timestampStr = ''
            
            dt = datetime.datetime.fromtimestamp(doc.timestamp)
            
            d  = datetime.date(dt.year, dt.month, dt.day)
            
            today = datetime.date.today()
            
            if today == d:
                
                timestampStr = 'Today, ' + dt.strftime("%H:%M") 
                
            elif today == d + datetime.timedelta(days=1):
                
                timestampStr = 'Yesterday, ' + dt.strftime("%H:%M")
                
            elif today <= d + datetime.timedelta(days=6): # file's date is in the past week, start with weekday
                
                timestampStr = dt.strftime("%a, %H:%M") 
                
            else: timestampStr = dt.strftime("%b %d %Y")
            
            QTableWidgetItem.__init__(self, timestampStr)
            
        else: QTableWidgetItem.__init__(self, str(doc.timestamp) )
        
        self.setFlags(Qt.ItemFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)) # make table fields "active" but NOT editable (as they by default are)
        
        self.setBackground(QBrush(QColor(222,223,222) ) ) # I find I can see the icons much better if the background is not white
        
        self.setToolTip("located in " + os.path.basename(os.path.dirname(doc.path)))
        self.doc = doc
        return
    
    pass

class MatchingDocsListWidget(NicerQTableWidget):
    
    def sortByColumn(self, col): # I override this function, since when the user clicks on the header of the (visible, human-friendly) "date" column I want to sort on the 3rd (hidden) col that contains all timestamps
                
        # experimenting with my school's webmail system suggests that
        
        # ==> "arrow point down" for dates means "most recent first"
        
        # ==> "arrow point down" for names means "reversal alphabetical order"
        
        # let us do that.
        
        # which GUI column currently has the little arrow indicating a sort direction (and in which direction does that arrow point?)
        # [notice that (as far as I understand) at this point these two values have already been set to reflect the user's click that 
        # triggered this call to sortByColumn]
        
        currIndicatorCol = self.horizHeader.sortIndicatorSection()
        currIndicatorOrder = self.horizHeader.sortIndicatorOrder()
        
        if col == 1: # was a click on the 'date' column
            
            # replicate the current 'sort indicator' settings in the hidden 'timestamp' column on which we will actually do the sorting
            
            self.horizHeader.setSortIndicator(2, currIndicatorOrder)
            
            # actually do the sorting; notice that to preserve the semantics of 'down arrow == most recent first' [which I prefer over Qt's]
            # AND to ensure that the first click on the date header always does 'most recent first' [which I find more useful than its opposite]
            # I invert the sort order that I pass to sortByColumn (this is the fruit of experimentation...)
            
            QTableView.sortByColumn(self, 2, Qt.DescendingOrder if currIndicatorOrder == Qt.AscendingOrder else Qt.AscendingOrder )
            
            # make the little arrow show up on the 'human-friendly' date column
            
            self.horizHeader.setSortIndicator(1, currIndicatorOrder) # THIS MUST BE HERE, otherwise sorting on date breaks
            
            pass
        
        else: # clicks on any other columns are handled normally
            
            QTableView.sortByColumn(self, col)
            pass                

        self.horizHeader.setSortIndicatorShown(True) # this is necessary and MUST be done anew every time we sort! [IE, LEAVE IT HERE]
        
        return

    
    def __init__(self, matchingDocsWidget, parent = None):
        
        # NOTE: If something done hear does not seem to work, that might be because of the self.listwidget.clear() call at the top of .update().
        # SOLUTION: place those actions (eg, qtablewidget configuration/setup) in .update()

        NicerQTableWidget.__init__(self, parent, matchingDocsWidget.showAppInMsgBar)    
        
        self.setIconSize(QSize(cfg.ICON_SIZE,cfg.ICON_SIZE) )
        
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff) # useless, does NOT ensure columns are the correct size (just makes what is outside of the viewport inaccessible)
        
        self.setColumnCount(3) # 1st col: icon+name, 2nd col: date for human-consumption, 3rd INVISIBLE col: timestamp (for sorting). column headers need to be set in update(), since the call to listwidget.clear() at the top of that function seems to reset the headers
        
        self.setColumnHidden(2, True) 
        
        self.setAlternatingRowColors(True)
        
        self.horizHeader = self.horizontalHeader()
        
        # try to setup the results pane (column widths, etc) so that is looks half decent
                
        self.horizHeader.resizeSection(1, 142) # fix the width of the date column to something reasonable (and which has enough space for the sort indicators to show up without cramping the text)
        self.horizHeader.setResizeMode(0, QHeaderView.Stretch) # document name col
        self.horizHeader.setResizeMode(1, QHeaderView.Fixed) # date col
                
        self.matchingDocsWidget = matchingDocsWidget
        
        self.resetSelectionWhenFocusChanges = True
        
        self.connect(self, SIGNAL("itemActivated(QTableWidgetItem*)"), self.matchingDocsWidget.openDoc)
        
        self.connect(self, SIGNAL("currentCellChanged(int,int,int,int)"), self.matchingDocsWidget.showAppInMsgBar)
        
        def docStoredInFunc(item): return "[located in %s]"%os.path.basename(os.path.dirname(item.doc.path))
        
        def opensByDefaultWithApp(item):
            
            return "[default app: %s]"%getDefaultAppCmdForExt(item.doc.extension)[0]
        
        self.addMenuAction(docStoredInFunc, lambda: True) # noop func; passing 3rd arg enabled=False makes it almost illegible on my system
        #self.addMenuAction(opensByDefaultWithApp, lambda: True) # noop func; passing 3rd arg enabled=False makes it almost illegible on my system
        self.addSeparator()
        self.addMenuAction("&Open doc with...",  self.matchingDocsWidget.openDocWith)
        self.addMenuAction("&Copy doc to...",  self.matchingDocsWidget.copyDocTo)
        self.addMenuAction("&Move doc to...",  self.matchingDocsWidget.moveDocTo)
        self.addMenuAction("&Remove doc",  self.matchingDocsWidget.removeDoc)
        self.addMenuAction("Rename/re&tag doc",  self.matchingDocsWidget.renameRetagDoc)
        return
    
    def keyPressEvent(self, event):
        
        if self.currentItem() == None or event.key() != Qt.Key_Return:
            
            NicerQTableWidget.keyPressEvent(self, event)
            
        elif self.currentItem() != None: self.matchingDocsWidget.openDoc()
        return      
    
    pass

class MatchingDocs(QWidget):
    
    def __init__(self, msgBar, parent = None):
        
        
        # NOTE: If something done hear does not seem to work, that might be because of the self.listwidget.clear() call at the top of .update().
        # SOLUTION: place those actions (eg, qtablewidget configuration/setup) in .update()
        
        QWidget.__init__(self, parent)
        
        self.maxResults = cfg.MAX_RESULTS
        
        self.msgBar = msgBar
        
        self.label = QLabel("Matching &%ss:"%cfg.nameOfItem)
        
        self.numberResultsButton = MyQPushButton("Sho&w +/-")
        horizBox = QWidget(self)
        horizBoxLayout = QHBoxLayout()
        horizBoxLayout.addWidget(self.label)
        horizBoxLayout.addWidget(self.numberResultsButton)
        horizBox.setLayout(horizBoxLayout)
        
        self.listwidget = MatchingDocsListWidget(self)
        self.listwidget.setEnabled(False)
        self.setFocusProxy(self.listwidget)
        
        self.label.setBuddy(self.listwidget)
        box = QVBoxLayout()
        box.addWidget(horizBox)
        box.addWidget(self.listwidget)
        self.setLayout(box)
        
        self.latestQueryResults = None # we keep around a list of the most recent query results; this allows us not to rerun the query just because the user changed maxResults
        
        self.connect(self.numberResultsButton, SIGNAL("clicked()"), self.doMaxResultsDialog)
        return
    
    def update(self, docs):
        
        self.listwidget.clearContents()        

        if len(docs) > 0:
            
            self.listwidget.setEnabled(True)
            
        else: self.listwidget.setEnabled(False)
        
        if cfg.TIMESTAMP_TO_USE == "mtime": dateLabel = "   Date modified   "
        elif cfg.TIMESTAMP_TO_USE == "atime": dateLabel = "   Date accessed   "
        else: dateLabel = "   Date   "
        
        # these additional whitespaces around the header labels ensure that when the sort symbol (down/up arrow) is shown there is enough space
        # for the header to remain fully visible
        
        self.listwidget.setHorizontalHeaderLabels( QStringList(['   Document name   ', dateLabel]) )
        
        s = "%d matching &%s%s: "%(len(docs), cfg.nameOfItem, 's' if len(docs) != 1 else '')
        
        if self.maxResults != None and len(docs) > self.maxResults:
            
            if self.maxResults == 1: s += "(showing most recent one)"
            else: s += "(showing %d most recent ones)"%self.maxResults
            pass
        
        else: s += "(showing all)"
        
        self.label.setText(s)

        self.listwidget.setSortingEnabled(False) # SEE BELOW; this must be OFF [previous comment: Qt docs suggest temporarily disabling sorting to make insertions easier]
        
        docsToList = docs[:self.maxResults] if self.maxResults != None else docs
        
        self.listwidget.setRowCount( len(docsToList) )
        
        for (rowNum, doc) in enumerate(docsToList):
            
            item = DocListWidgetItem(doc, "ICON_AND_NAME")
            self.listwidget.setItem(rowNum, 0, item)
            item = DocListWidgetItem(doc, "DATE")
            self.listwidget.setItem(rowNum, 1, item )
            item = DocListWidgetItem(doc, "TIMESTAMP")
            self.listwidget.setItem(rowNum, 2, item )
            pass                
        
        
        # if I had found a way to override the QTableView.sortByColumn, I wouldn' need this clunk; but currently that is what I have. I simply
        # leave sorting 'disabled' and manually tie clicks on the header to my own sortByColumn (which handles clicks on the date column especially)
        
        #self.listwidget.setSortingEnabled(True) # LEAVE THIS OFF/COMMENTED; otherwise, it messes up our trick to correctly sort by date
        
        self.connect( self.listwidget.horizontalHeader(), SIGNAL("sectionClicked(int)"), self.listwidget.sortByColumn)
        
        self.latestQueryResults = docs
        return
    
    def doMaxResultsDialog(self):
        
        maxResults,okPressed = QInputDialog.getText(self, "Limit results to...", \
        "How many matching docs should be listed?\n(Enter 'all' to show all matches.)\nDefault: %d"%(cfg.MAX_RESULTS))
        
        if not okPressed: return
        
        maxResults = str(maxResults)
        
        if maxResults.strip().lower() == 'all': maxResults = None # no limit
        
        else:
            try: 
                maxResults = int(maxResults)
                if maxResults <= 0: raise ValueError
                pass
            
            except ValueError: 
                QMessageBox.warning(None, "oyepa", "Doesn't look like a valid number to me!")
                return
            pass
        
        if maxResults != self.maxResults:
            
            self.maxResults = maxResults
            self.update(self.latestQueryResults) # don't run the query again, simply use the results we stored!
            pass
        
        return
    
    
    def showAppInMsgBar(self, *additionalArgs): # this gets called from a slot that insists in passing us 4 args we don't care about
        
        item = self.listwidget.currentItem()
        
        if item == None: msg = ""
        
        else:
            if item.doc.extension == None: msg = "" # stay quiet if we don't know what the file type is
            
            else:
                
                app = getDefaultAppCmdForExt(item.doc.extension)[0]
                
                msg = "." + item.doc.extension
                if app != None:  msg += ", opens with " + app
                else:            msg += ", no default app"
                pass
            pass
        
        self.msgBar.setText(msg)
        return
    
    def openDocWith(self):
        
        item = self.listwidget.currentItem()
        
        if item == None: return
        
        path = item.doc.path
        
        dial = AppCmdDialog(item.doc.extension, os.path.isdir(path), self)
        
        retval = dial.exec_()
        
        if retval == QDialog.Rejected: return
        
        cmd = dial.getCmd()
        
        if os.path.isdir(path) and \
        dial.getAppName() == cfg.TERMINAL_HACK and len(cmd) == 0: # means this is an appeal to our built-in "open xterm with cwd=dir-doc I just selected" hack (ahem, "feature"!)
            
            run_cmd_on_path(None, path, usingTermHack=True)
            
        elif len(cmd) > 0: run_cmd_on_path(cmd, path) # general case
        
        return
    
    
    def openDoc(self):
        
        item = self.listwidget.currentItem()
        
        if item == None: return
        
        app, cmd = getDefaultAppCmdForExt(item.doc.extension)
        
        if cmd != None: run_cmd_on_path(cmd, item.doc.path)
        
        elif app == cfg.TERMINAL_HACK: run_cmd_on_path(None, item.doc.path, usingTermHack=True)
        
        else: self.openDocWith()
        
        return
    
    def copyDocTo(self):
        
        item = self.listwidget.currentItem()
        
        if item == None: return
        
        dial = GetCopyMoveDestinationDialog(item, "Copy to...", "Place a copy of this doc in dir...", "Copy of doc will be named")
        
        destPath = dial.getDestinationPath()
        
        if destPath == None: return
        
        retval = copyDocTo(item.doc.path, destPath)
        
        if retval != None: QMessageBox.warning(None, "Error", retval)
        else: QMessageBox.information(None, "Copy to...", "A copy of this doc was saved as " + destPath)
        
        self.emit(SIGNAL("docCopiedMovedRemoved()")) # this triggers an absolutely idiotic call to runQuerySlot; embarassingly inefficient. Those interested should consider taking a more piecemeal approach to updating the list of matching docs
        
        return
    
    def moveDocTo(self):
        
        item = self.listwidget.currentItem()
        
        if item == None: return
        
        dial = GetCopyMoveDestinationDialog(item, "Move to...", "Move this doc to dir...", "Doc will be named")
        
        destPath = dial.getDestinationPath()
        
        if destPath == None: return
        
        allTagsBeforeRenaming = getAllTags()
        
        retval = moveDocTo(item.doc.path, destPath)
        
        if retval != None: 
            QMessageBox.warning(None, "Error", retval)
            return
        
        QMessageBox.information(None, "Move to...", "Doc is now located at " + destPath)
        
        self.emit(SIGNAL("docCopiedMovedRemoved()")) # this triggers an absolutely idiotic call to runQuerySlot; embarassingly inefficient. Those interested should consider taking a more piecemeal approach to updating the list of matching docs
        
        # Finally, tagSelector wants to know this; it might need to remove some tags from its two QListWidgets
        
        if allTagsBeforeRenaming != getAllTags():
            print "moveDocTo() emitting 'setOfAllTagsChanged()'"
            self.emit(SIGNAL("setOfAllTagsChanged()"))
            pass
        
        else: print "moveDocTo() NOT emitting 'setOfAllTagsChanged()'"
        
        return
    
    def removeDoc(self):
        
        item = self.listwidget.currentItem()
        
        if item == None: return
        
        question = "Are you sure you want to delete doc %s?"%item.doc.docname
        if os.path.isdir(item.doc.path): question += "\nWARNING: this doc is a directory!"
        
        button = QMessageBox.question(self, "Warning", question, QMessageBox.Yes|QMessageBox.No, QMessageBox.No)
        
        if button != QMessageBox.Yes: return
        
        allTagsBeforeRemoval = getAllTags()
        
        # let oyepa-filemon know that we really mean it (ie, that tags-cache 
        # should be updated immediately, no use of recently_disappeared, etc)
        
        retval = removeDoc(item.doc.path)
        
        if retval != None: 
            QMessageBox.warning(None, "Error", retval)
            return
        
        self.emit(SIGNAL("docCopiedMovedRemoved()")) # this triggers an absolutely idiotic call to runQuerySlot; embarassingly inefficient. Those interested should consider taking a more piecemeal approach to updating the list of matching docs
        
        # Finally, tagSelector wants to know this; it might need to remove some tags from its two QListWidgets
        
        if allTagsBeforeRemoval != getAllTags(): 
            print "removeDoc() emitting 'setOfAllTagsChanged()'"
            self.emit(SIGNAL("setOfAllTagsChanged()"))
            pass
        else: print "removeDoc() NOT emitting 'setOfAllTagsChanged()'"
        
        return
    
    def renameRetagDoc(self):
        
        item = self.listwidget.currentItem()
        
        if item == None: return
        
        allTagsBeforeRemoval = getAllTags()
        
        do_tagger(item.doc.path, self)
        
        self.emit(SIGNAL("docCopiedMovedRemoved()")) # this triggers an absolutely idiotic call to runQuerySlot; embarassingly inefficient. Those interested should consider taking a more piecemeal approach to updating the list of matching docs
        
        # Finally, tagSelector wants to know this; it might need to remove some tags from its two QListWidgets
        
        if allTagsBeforeRemoval != getAllTags(): 
            print "renameRetagDoc() emitting 'setOfAllTagsChanged()'"
            self.emit(SIGNAL("setOfAllTagsChanged()"))
            pass
        else: print "renameRetagDoc() NOT emitting 'setOfAllTagsChanged()'"
        
        return
    
    pass


def do_tagger(path, parentWindow = None):
    
    dialog = QDialog(parentWindow)
    
    # get  most current purename and tags of the file referenced by this path
    
    purename, origTags, metadataMoreRecentThanFilename = \
    getCurrentPureNameAndTagsForDoc(path)
    
    if purename == None or not os.path.exists(path):
        
        QMessageBox.critical(None, "oyepa", \
        "oyepa received an invalid path as an arg.\nPath: " + path)
        return False
    
    elif metadataMoreRecentThanFilename and parentWindow == None: # if parentWindow != None, then we were called through a right-click in the document browser locator; no need to warn user about the path not reflecting the most useful metadata.
        
        QMessageBox.warning(None, "oyepa", "Using more recent metadata for this doc than the one inscribed into its path!")
        pass
    
    # set up interface
    
    dialog.setWindowTitle("Tag this doc?")
    
    winLayout = QVBoxLayout()
    
    topBox = QWidget()
    
    topBoxLayout = QHBoxLayout()
    
    # buttons
    
    buttonBox = QWidget()
    buttonBoxLayout = QVBoxLayout()
    doneButton = MyQPushButton("Done (Alt-&Q)")
    doneButton.setAutoDefault(False) # important! otherwise pressing 'enter' anywhere (eg, upon entering a tag in the taglineedit) will trigger the GUI to 'press' this button
    leaveButton = MyQPushButton("&Leave unchanged")
    leaveButton.setAutoDefault(False) # important! otherwise pressing 'enter' anywhere (eg, upon entering a tag in the taglineedit) might trigger the GUI to 'press' this button
    buttonBoxLayout.addWidget(doneButton)
    buttonBoxLayout.addWidget(leaveButton)
    buttonBox.setLayout(buttonBoxLayout)
    
    docNameWidget = DocNameWidget(purename)
    topBoxLayout.addWidget(docNameWidget)
    topBoxLayout.addWidget(buttonBox)
    topBox.setLayout(topBoxLayout)
    
    msgBar = QLabel()
    msgBar.setText("Ready")
    
    tagSelector = TagSelector("&Add tag:", msgBar, preselectedTags=origTags)
    
    winLayout.addWidget(topBox)
    winLayout.addWidget(tagSelector)
    
    winLayout.addWidget(msgBar)
    
    dialog.setLayout(winLayout)
    
    # instantiate the object which will actually tag the file if the user presses
    # the "done" button
    
    # connect buttons
    
    def tagDocSlot(): 
        
        print "tagDocSlot() invoked"
        retval = tagDoc(path, docNameWidget.getDocName(), \
        tagSelector.getSelectedTags(), origTags)
        
        if type(retval) == str:  
            
            QMessageBox.warning(None, "oyepa", retval)
            docNameWidget.switchToLineEdit()
            
        else: dialog.accept()
        
        return
    
    QObject.connect(doneButton, SIGNAL("clicked()"), tagDocSlot)
    
    QObject.connect(leaveButton, SIGNAL("clicked()"), dialog, SLOT("reject()"))
    
    def disableDoneButton(): doneButton.setEnabled(False)
    def enableDoneButton(): doneButton.setEnabled(True)
    
    QObject.connect(docNameWidget, SIGNAL("goodDocName()"), enableDoneButton)
    QObject.connect(docNameWidget, SIGNAL("badDocName()"), disableDoneButton)
    
    QWidget.setTabOrder(docNameWidget.nameLineEdit, tagSelector.tagLineEdit)
    QWidget.setTabOrder(tagSelector.tagLineEdit, tagSelector.selectedListView)
    QWidget.setTabOrder(tagSelector.selectedListView, doneButton)
    QWidget.setTabOrder(doneButton, leaveButton)
    
    tagSelector.tagLineEdit.setFocus()
    
    return dialog.exec_()


def do_search(dirsInCmdLine, parentWindow = None):
    
    # set up interface
    
    win = QWidget(parentWindow);
    win.setWindowTitle(cfg.searchWindowTitle)
    
    if cfg.runInFullScreenMode: win.showFullScreen()
    
    winLayout = QVBoxLayout()
    
    dirSelector = None
    
    doc_dirs = getDocDirs()
    doc_dir_hierarchy = getDocDirHierarchy()
    
    if len(doc_dir_hierarchy) > 1:
        
        dirSelector = DirSelector(doc_dir_hierarchy, dirsInCmdLine)

    elif not doc_dir_hierarchy:
        
        QMessageBox.critical(None, "oyepa", \
        "Before using oyepa, you need to tell it where to find your documents.\n\nTo try it out, do the following:\n\n 1- create the file %s and add a line\n\n~/docs\n\n2- create a directory 'docs' in your home dir." % cfg.FILENAME_LISTING_DOC_DIRS)
        return False
    
    msgBar = QLabel()
    msgBar.setText("Ready")
    
    tagSelector = TagSelector("&Search for:", msgBar, [])
    leaveButton = MyQPushButton(cfg.leaveButtonCaption)
    
    topBox = QWidget()
    middleBox = QWidget()
    
    topBoxLayout = QHBoxLayout()
    
    if dirSelector != None: topBoxLayout.addWidget(dirSelector)
    
    topBoxLayout.addWidget(tagSelector)
    topBoxLayout.addWidget(leaveButton)
    topBox.setLayout(topBoxLayout)
    
    middleBoxLayout = QHBoxLayout()
    
    untaggedButton = MyQCheckBox("List &untagged")
    untaggedButton.setFocusPolicy(Qt.NoFocus)
    widgetWithFocusBeforeUntaggedButtonToggled = None        
    
    updateDocsButton = MyQPushButton("&Update Files");

    matchingDocsList = MatchingDocs(msgBar)
    
    winLayout.addWidget(topBox)
    
    if cfg.ExtensionsWidgetClassToUse != None: 
        
        extensionsWidget = globals()[cfg.ExtensionsWidgetClassToUse](); # HACK ALERT
        winLayout.addWidget(extensionsWidget)
        
    else: extensionsWidget = None
    
    winLayout.addWidget(untaggedButton)
    winLayout.addWidget(updateDocsButton)
    winLayout.addWidget(matchingDocsList)
    winLayout.addWidget(msgBar)
    
    win.setLayout(winLayout)
    win.show()
    
    # now draw up a bunch of signal-slot connections
    
    if cfg.DONT_QUIT_INSTEAD_EXECUTE_CMD: # if this is set, pressing the leaveButton does not exit the application but instead executes the cmd DONT_QUIT_INSTEAD_EXECUTE_CMD in a shell
        
        win.doLeaveButton = lambda: os.system(cfg.DONT_QUIT_INSTEAD_EXECUTE_CMD)
        
    else: win.doLeaveButton = win.close # default case, pressing "Leave" closes the window (and the app)
    
    QObject.connect(leaveButton, SIGNAL("clicked()"), win.doLeaveButton)
    
    escapeKeyPressed = QShortcut(Qt.Key_Escape, win)
    app.connect(escapeKeyPressed, SIGNAL("activated()"), win.doLeaveButton)
    
    QObject.connect(updateDocsButton, SIGNAL("clicked()"), update_files)

    # and those which prompt an update of the list of matching docs
    
    def runQuerySlot():
        
        class RunQueryThread(ThreadWithPleaseWaitMessage):
            
            def run(self):
                
                self.matches = runQuery(            \
                tagSelector.getSelectedTags(),      \
                extensionsWidget.getExtensions() if extensionsWidget != None else [], \
                dirSelector.getSelectedDirs() if dirSelector != None else None,
                untaggedButton.checkState() == Qt.Checked)
                return
            pass
        
        runQueryThread = RunQueryThread(msgBar)
        
        runQueryThread.execute() # blocks until IO thread finishes
        
        matchingDocsList.update(runQueryThread.matches)
        
        # if we are listing untagged docs, place focus on doc list (if there are any matches)
        
        if untaggedButton.checkState() == Qt.Checked and \
        len(runQueryThread.matches) > 0:
            
            matchingDocsList.setFocus()
            pass
        
        return
    
    def enableDisableTagSelectorAndReRunQuery():
        
        global widgetWithFocusBeforeUntaggedButtonToggled # I don't really understand why, but this global statement makes this var accessible for reading inside this var
        
        if untaggedButton.checkState() == Qt.Unchecked:
            
            tagSelector.setEnabled(True)
            
            if widgetWithFocusBeforeUntaggedButtonToggled != None:
                widgetWithFocusBeforeUntaggedButtonToggled.setFocus()
                pass
            pass
        
        else: # untaggedButton.checkState() == Qt.Checked:
            
            widgetWithFocusBeforeUntaggedButtonToggled = QApplication.focusWidget()
            tagSelector.setEnabled(False)
            pass
        
        runQuerySlot()
        return
    
    QObject.connect(tagSelector, SIGNAL("tagSelected(QString)"), runQuerySlot)
    QObject.connect(tagSelector, SIGNAL("tagDeselected(QString)"), runQuerySlot)
    QObject.connect(tagSelector, SIGNAL("setOfAllTagsChanged()"), runQuerySlot)
    
    QObject.connect(matchingDocsList, SIGNAL("docCopiedMovedRemoved()"), runQuerySlot)
    
    QObject.connect(matchingDocsList, SIGNAL("setOfAllTagsChanged()"), tagSelector.updateAfterChangesToSetOfAllTags)
    
    if extensionsWidget != None: QObject.connect(extensionsWidget, SIGNAL("extensionListChanged()"), runQuerySlot)
    
    if dirSelector != None: QObject.connect(dirSelector, SIGNAL("selectedDirsChanged()"), runQuerySlot)
    
    
    QObject.connect(untaggedButton, SIGNAL("stateChanged(int)"), enableDisableTagSelectorAndReRunQuery)
    
    
    initialDocList = runQuery(None, extensionsWidget.getExtensions() if extensionsWidget != None else None, \
    dirSelector.getSelectedDirs() if dirSelector != None else None)
    
    matchingDocsList.update(initialDocList)
    
    QWidget.setTabOrder(leaveButton, tagSelector.tagLineEdit)
    QWidget.setTabOrder(tagSelector.tagLineEdit, tagSelector.selectedListView)
    
    if extensionsWidget != None: 
        
        QWidget.setTabOrder(tagSelector.selectedListView, extensionsWidget)
        QWidget.setTabOrder(extensionsWidget, matchingDocsList)
        
    else: QWidget.setTabOrder(tagSelector.selectedListView, matchingDocsList)
    
    if dirSelector != None: 
        
        QWidget.setTabOrder(matchingDocsList, dirSelector)
        QWidget.setTabOrder(dirSelector, leaveButton)
        
    else: QWidget.setTabOrder(matchingDocsList, leaveButton)
    
    tagSelector.tagLineEdit.setFocus()
    
    return app.exec_()


def print_help():
    
    print "usage: oyepa                         run in search mode"
    print "       oyepa --dirs dir1 [dir2...]   run in search mode restricted to listed dirs"
    print "       oyepa path_to_doc             run in (re)tag doc mode"
    print "       oyepa --rebuild_tag_cache     rebuild tag cache for all doc dirs"
    return

if __name__=="__main__": #and False: # enable this to run pychecker
    
    #run_cmd_on_path()
    #return    
    
    app = QApplication(sys.argv)
    
    sys.excepthook = gui_excepthook
    
    app.connect(qApp, SIGNAL("lastWindowClosed()"), qApp, SLOT("quit()"))
    
    if len(sys.argv) == 1 or sys.argv[1] == "--dirs": 
        
        dirsInCmdLine = []
        
        if len(sys.argv) > 1: # user specified narrowed down the set of doc-dirs to work with
            
            dirsInCmdLine = filter(os.path.exists, sys.argv[2:])
            
            if len(dirsInCmdLine) < len(sys.argv) - 2:
                
                QMessageBox.warning(None, "oyepa", "Some of the dirs specified in the command line do not exist!")
                pass
            pass
        
        sys.exit(do_search(dirsInCmdLine))
        
    elif len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        
        print_help()
        sys.exit(0)
        
    elif len(sys.argv) == 2 and sys.argv[1] == "--rebuild_tag_cache":
        
        print "Please wait, this might take a while..."
        rebuildTagCache()
        print "Done."
        
    elif len(sys.argv) == 2 and not sys.argv[1].startswith("-"): sys.exit(do_tagger(sys.argv[1]))
    
    else:
        
        app = QApplication(sys.argv)
        QMessageBox.critical(None, "oyepa", \
        "oyepa called with invalid args!\nArgs: " + " ".join(sys.argv[1:]))
        print_help()
        sys.exit(1)
        pass
    
    pass

