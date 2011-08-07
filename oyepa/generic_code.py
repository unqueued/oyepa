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

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from fslayer import readDocDirList, read_pending_updates, write_pending_updates

import os
import sys, string, traceback # for the gui_excepthook function implemented below

import cfg

def update_files():
    doc_dirs = readDocDirList()
    for doc_dir in doc_dirs:
            
        updates_dic = read_pending_updates(doc_dir)
            
        for orig, new in updates_dic.copy().items(): # doesn not look like it is necessary, but let us iterate over a  copy of the dic just to be safe (since we will be removing items)
                
            oldpath = os.path.join(doc_dir, orig)
            newpath = os.path.join(doc_dir, new)
                
            if os.path.exists(newpath): 
                    
                print "Skipping update of doc %s since newpath (%s) already exists"%(oldpath,newpath)
                    
            elif not os.path.exists(oldpath): 
                    
                print "Couldn't find doc %s, won't update it"%oldpath
                    
            else:
                    
                try: os.rename(oldpath, newpath)
                except Exception, e: print "Unable to rename %s to %s [%s]"%(oldpath,newpath,str(e))
                    
                pass
            pass
            
        write_pending_updates(doc_dir, {}) # IMPORTANT!! : )
            
        # finally, just remove the "internal ops" list file that might be lying around
            
        oyepa_internal_ops_filepath = \
        os.path.join(doc_dir, cfg.oyepa_internal_ops_filename)
            
        if os.path.exists(oyepa_internal_ops_filepath):
                
            try: os.unlink(oyepa_internal_ops_filepath)
            except: print "Unable to remove an immediate disappearances file [%s]"%oyepa_internal_ops_filepath
            pass
        pass


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

class MyQPushButton(QPushButton):
    
    def __init__(self, label):
        
        QPushButton.__init__(self, label)
        return
    
    def keyPressEvent(self, event):
        
        if event.key() == Qt.Key_Return: self.animateClick()
        
        QPushButton.keyPressEvent(self, event)
        return
    pass

class MyQCheckBox(QCheckBox):
    
    def __init__(self, label):
        
        QCheckBox.__init__(self, label)
        return
    
    def keyPressEvent(self, event):
        
        if event.key() == Qt.Key_Return: self.animateClick()
        
        QCheckBox.keyPressEvent(self, event)
        return
    pass

class NicerQListWidget(QListWidget):
    
    def __init__(self, parent = None, onFocusOutCallFunc = None): # XXX on focusOut, call passed function?
        
        QListWidget.__init__(self, parent)
        self.menu_actions = []
        self.onFocusOutCallFunc = onFocusOutCallFunc
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        return
    
    def getItems(self):
        
        items = []
        
        for i in range(self.count()): items.append(unicode(self.item(i).text().toUtf8(), 'utf-8').lower().strip())
        
        return items
    
    def focusInEvent(self, event):
        
        if event.reason() not in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason):
            
            self.setCurrentRow(0)
            pass
        
        QListWidget.focusInEvent(self, event)
        return
    
    def focusOutEvent(self, event):
        
        if event.reason() not in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason):
            
            self.clearSelection()
            self.setCurrentItem(None)
            pass
        
        if self.onFocusOutCallFunc != None: self.onFocusOutCallFunc()
        QListWidget.focusOutEvent(self, event)
        return
    
    def addMenuAction(self, label, fun, enabled = True): # if 'label' is a function, then that function is invoked (with the item on which the right-button was clicked as its sole argument) to generate the label
        
        self.menu_actions.append((label,fun, enabled))
        return
    
    def addSeparator(self): self.menu_actions.append((None,None,None))
    
    def mousePressEvent(self, event):
        
        item = self.itemAt(event.pos())
        QListWidget.mousePressEvent(self, event)
        
        if item != None and event.button() == Qt.RightButton:
            
            self.setCurrentItem(item)
            self.menu=QMenu(self)
            
            for label , action , enabled in self.menu_actions:
                
                if label == action == enabled == None:
                    
                    self.menu.addSeparator()
                    continue
                
                if str(type(label)) == "<type 'function'>": # ugly, but couldn't figure out the type of a function
                    
                    actualLabel = label(item) 
                    a = self.menu.addAction(actualLabel, action)
                    
                else: a = self.menu.addAction(label, action)
                
                a.setEnabled(enabled)
                pass
            
            self.menu.popup(event.globalPos())
            pass        
        
        return
    
    pass


class NicerQTableWidget(QTableWidget):
        
    def __init__(self, parent = None, onFocusOutCallFunc = None): # XXX on focusOut, call passed function?
        
        QTableWidget.__init__(self, parent)
        self.menu_actions = []
        self.onFocusOutCallFunc = onFocusOutCallFunc
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        return
    
    def getItems(self):
        
        items = []
        
        for i in range(self.count()): items.append(unicode(self.item(i).text().toUtf8(),'utf-8').lower().strip())
        
        return items
    
    def focusInEvent(self, event):
        
        if event.reason() not in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason):
            
            self.setCurrentCell(0,0)
            pass
        
        QTableWidget.focusInEvent(self, event)
        return
    
    def focusOutEvent(self, event):
        
        if event.reason() not in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason):
            
            self.clearSelection()
            self.setCurrentItem(None)
            pass
        
        if self.onFocusOutCallFunc != None: self.onFocusOutCallFunc()
        QTableWidget.focusOutEvent(self, event)
        return
    
    def addMenuAction(self, label, fun, enabled = True): # if 'label' is a function, then that function is invoked (with the item on which the right-button was clicked as its sole argument) to generate the label
        
        self.menu_actions.append((label,fun, enabled))
        return
    
    def addSeparator(self): self.menu_actions.append((None,None,None))
    
    def mousePressEvent(self, event):
        
        item = self.itemAt(event.pos())
        
        QTableWidget.mousePressEvent(self, event)
        
        if item != None and event.button() == Qt.RightButton:
            
            self.setCurrentItem(item)
            self.menu=QMenu(self)
            
            for label , action , enabled in self.menu_actions:
                
                if label == action == enabled == None:
                    
                    self.menu.addSeparator()
                    continue
                
                if str(type(label)) == "<type 'function'>": # ugly, but couldn't figure out the type of a function
                    
                    actualLabel = label(item) 
                    a = self.menu.addAction(actualLabel, action)
                    
                else: a = self.menu.addAction(label, action)
                
                a.setEnabled(enabled)
                pass
            
            self.menu.popup(event.globalPos())
            pass        
        
        return
    
    pass



# (almost) straight from the PyKDE mailing list archives : )
# my thanks to Ulrich Berning.
# Defining this function and setting sys.excepthook to it allows us to receive 
# reports of exceptions in the GUI.

def gui_excepthook(exc_type, exc_value, exc_traceback):
    
    msg = string.joinfields(traceback.format_exception(exc_type, exc_value, exc_traceback))
    QMessageBox.critical(None, sys.argv[0],"An exception occurred!\n" + str(msg))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)
    qApp.quit()
    return

# these RadioButtons are "enterable", meaning that pressing the Enter key on an item will run 
# uponClickRunFunc (useful to easily accept a dialog upon selecting a button)

class MyQRadioButton(QRadioButton): 
    
    def __init__(self, label, uponClickRunFunc):
        
        QRadioButton.__init__(self, label)
        self.uponClickRunFunc = uponClickRunFunc
        return
    
    def keyPressEvent(self, event):
        
        if event.key() == Qt.Key_Return: 
            
            self.animateClick()
            self.uponClickRunFunc()
            
        else: QRadioButton.keyPressEvent(self, event)
        return
    pass


# this function runs a dialog prompting the user to select one option from
# a list of (My)QRadioButtons. Returns either False (if the dialog is dismissed)
# or the text of the selected button.

def runYesNoCheckBoxesDialog(promptText, options, initiallyCheckedOption):

    dial = QDialog(None)
    layout = QVBoxLayout()
    label = QLabel(promptText)
    layout.addWidget(label)
    buttonGroup = QButtonGroup()
    buttonGroup.setExclusive(True)
    
    for option in options:
        
        cbox = MyQRadioButton(option, dial.accept)
        if option == initiallyCheckedOption: cbox.setChecked(True)
        layout.addWidget(cbox)
        buttonGroup.addButton(cbox)
        pass
    
    buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    
    QObject.connect(buttonBox, SIGNAL("accepted()"), dial.accept)
    QObject.connect(buttonBox, SIGNAL("rejected()"), dial.reject) 
    
    layout.addWidget(buttonBox)
    
    dial.setLayout(layout)
    retval = dial.exec_()
    
    if retval == QDialog.Rejected: return False
    else: return buttonGroup.checkedButton().text()
    pass
