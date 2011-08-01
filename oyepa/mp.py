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

import os, re, sys, time, user

import pexpect

from PyQt4.QtGui import *
from PyQt4.QtCore import *

# this program takes one arg: either the path to an album directory or to a ".radio" file. 
# In the former case, it will play all music files underneath it in the right order according
# to a number of filename-based "heuristics" (too fancy a name for such simple rules...). In
# the latter, case it expects to read the address of an INternet radio station from that 
# file and will try playing from it.

supportedFileFormats = ['mp3', 'ogg', 'aac', 'rmj', 'flac', 'wav', 'wma', 'mpc', 'ape', "m4a"]

fifoPath = os.path.join(user.home, ".mp.fifo")

lockFilePath = os.path.join(user.home, ".mp.lock") # to prevent multiple instances from running simultaneously

removeLockFileUponExiting = True # this is set to False when we detect that another instance is running so that we don't remove its lock file

app = None

class MyQListWidgetItem(QListWidgetItem):
    
    def __init__(self, text, path):
        
        QListWidgetItem.__init__(self, text)
        self.path = path # when path == None, that means it is a 'disc dir' entry
        return
    
    pass

class AlbumPlayer(QListWidget):
    
    def __init__(self, playLists, pausedWarningLabel, repeatModeLabel):
        
        QListWidget.__init__(self)
        
        self.playLists = playLists
        
        self.pausedWarningLabel = pausedWarningLabel
        self.repeatModeLabel = repeatModeLabel
        
        self.lastPathWeToldMplayerToPlay = None
        self.isPaused = False
        self.inRepeatMode = False
        
        for pl in playLists:
            
            if not pl.isTopLevel: self.addItem(MyQListWidgetItem(pl.name, None))
            
            for track in pl.tracks:
                
                self.addItem(MyQListWidgetItem((" " if not pl.isTopLevel else "") + os.path.splitext(os.path.basename(track))[0], track))
                pass
            pass
        
        # set us on the first track (the 'mplayer<->GUI sync' thread will get mplayer playing it)
        
        self.setCurrentRow(0)
        
        # setup the fifo through which we will talk to mplayer (PART I)
        
        if os.path.exists(fifoPath): os.unlink(fifoPath)
        os.mkfifo(fifoPath)
        
        # start mplayer
        
        global mplayer
        
        # -quiet (NOT -really-quiet, otherwise it won't reply to info requests sent via the FIFO) is important, since 
        # otherwise mplayer's status bar (which is permanently updated) messes up pexpect
        
        cmd = "mplayer -ao alsa -slave -quiet -idle -input file=%s"%fifoPath
        
        time.sleep(0.2)
        self.mplayer = pexpect.spawn(cmd)
        
        # setup the fifo for instructing MPlayer what to do (PART II)
        
        self.fifo = open(fifoPath, 'w')
        
        # start 'mplayer<->GUI sync' thread
        
        self.timer = QTimer(self)
        self.connect(self.timer, SIGNAL("timeout()"), self.updateCurrentTrack)
        self.timer.start(2000) # IMPORTANT! MAKE THIS INTERVAL TOO SHORT AND MPLAYER WILL SEEM (TO THE UPDATE... FUNCTION BELOW) TO BE DONE WITH PLAYING A TRACK, WHILE IN REALITY IT WON'T HAVE STARTED YET! 
        # TO ADD TO THE CONFUSION, MPLAYER SEEMS TO TAKE LONGER TO DECODE WEIRD PROPRIETARY FORMATS SUCH AS MPC; THAT LEAD ME TO BELIEVE THAT
        # THE PROBLEM WAS THAT MPLAYER WASN'T BEING ABLE TO READ THOSE FILES -- WRONG! TROUBLE WAS THAT THE CODE BELOW WHICH
        # CHECKS FOR MPLAYER TO BE DONE PLAYING A FILE CONCLUDED THAT MPLAYER HAD ALREADY FINISHED READING IT WHEN IT HADN'T EVEN
        # STARTED!
        
        return
    
    def quit(self):
        
        if self.mplayer != None: self.mplayer.close()
        qApp.quit() # we are done
        return
    
    def moveDownIfPossible(self):
        
        self.isPaused = False
        
        #print "moving down" #DEBUG
        if self.currentRow() + 1 == self.count(): self.quit()
        
        else: self.setCurrentRow(self.currentRow()+1) # move to first track on this 'disc' dir entry
        
        return
    
    def updateCurrentTrack(self):
        
        itemPath = self.currentItem().path  # this is the path of the item currrently selected in the GUI
        
        if itemPath == None: #  GUI is currently 'resting' on a 'disc' dir entry
            
            self.moveDownIfPossible()
            
        elif itemPath == self.lastPathWeToldMplayerToPlay: # GUI is 'pointing' to a track and the most recent thing we did was to tell mplayer to play that same track; is it still playing it?
            
            # this weird "not self.isPaused" is necessarily, since mplayer, WHILE PAUSED, actually plays for a fraction of a second whenever it gets one of the get_file_name/get_time_pos requests that are emitted by self.currentlyPlaying -- and that function runs quickly enough for the music to keep playing unstopped!
            
            if not self.isPaused and self.currentlyPlaying()[0] == None: # mplayer already finished playing this track, update GUI
                
                if self.inRepeatMode:
                    #print "loading " + re.escape(itemPath) #DEBUG
                    self.sendCmdToMplayer("loadfile " + re.escape(itemPath))
                    
                else: self.moveDownIfPossible() 
                pass
            
            else: # we are either paused (hence, it doesn't matter right now what we are 'playing'...) or we are playing what we say we are playing
                
                #print "UP doing nothing PAUSE STATUS: " + str(self.isPaused) #DEBUG
                return
            pass
        
        else: # tell mplayer to play whatever track is currently selected, which is NOT the track which me most recently told it to play
            
            self.lastPathWeToldMplayerToPlay = itemPath
            
            #print "DEBUG#@# loading " + re.escape(itemPath) #DEBUG
            #self.sendCmdToMplayer("loadfile /music-test/01.mpc")
            self.sendCmdToMplayer("pausing_keep loadfile " + re.escape(itemPath))
            pass
        
        return
    
    def currentlyPlaying(self):
        
        self.sendCmdToMplayer("pausing_keep get_file_name")
        try: self.mplayer.expect("ANS_FILENAME='(.*)'", timeout=0.1)
        except pexpect.TIMEOUT: return None, None
        
        filename = str(self.mplayer.match.group(1))
        
        # PERHAPS ENABLE XXX -- WATCH OUT FOR FORMATS (EG, MPC) which do not support seeking 
        #self.sendCmdToMplayer("pausing_keep get_time_pos")
        #try: self.mplayer.expect("ANS_TIME_POSITION=(.*)", timeout=0.1)
        #except pexpect.TIMEOUT: return None, None
        
        #time = self.mplayer.match.group(1).strip()
        time=None
        return filename, time
    
    def keyPressEvent(self, event):
        
        if event.key() == Qt.Key_Q: self.quit()           
        
        elif event.key() == Qt.Key_Space:
            
            if self.isPaused: self.pausedWarningLabel.setText("")
            else: self.pausedWarningLabel.setText(QString("<b> --- PAUSED ---</b>"))
            
            self.isPaused = not self.isPaused
            self.sendCmdToMplayer("pause") # same cmd also unpauses
            
        elif event.key() == Qt.Key_R: 
            
            if self.inRepeatMode: self.repeatModeLabel.setText("")
            else: self.repeatModeLabel.setText(QString("<b> --- REPEAT MODE ---</b>"))
            self.inRepeatMode = not self.inRepeatMode
            
        else: QListWidget.keyPressEvent(self, event)
        
        return
    
    def sendCmdToMplayer(self, cmd):
        
        #print "SEND " + cmd # DEBUG
        self.fifo.write(cmd + "\n")
        self.fifo.flush() # important -- and the source of great (now past) misery!
        return
    
    pass




################

class PlayList:
    
    def __init__(self, directory, tracks, isTopLevel):
        
        self.name = os.path.basename(directory)
        self.tracks = tracks
        self.isTopLevel = isTopLevel
        
        pass
    def __str__(self): return self.name + ":\n" + "\n".join(self.tracks)
    
    pass

def getTrackNumber(file):
    
    n = ""
    
    for c in file:
        
        if c.isdigit(): n += c
        elif len(n) == 0: continue
        else: break
        pass
    
    return int(n) if len(n) > 0 else 0

def sortMusicItemsInDir(directory, dirsOrFiles):
    
    items = os.listdir(directory)
    
    if   dirsOrFiles == "dirs":  f = lambda i: os.path.isdir( os.path.join(directory, i))
    
    elif dirsOrFiles == "files": f = lambda i: os.path.isfile(os.path.join(directory, i)) and os.path.splitext(i)[1][1:].lower() in supportedFileFormats
    
    else: assert False, "sortMusicItemsInDir() called with invalid second arg (%s)"%dirsOrFiles
    
    items = filter(f, items)
    
    items.sort(key = getTrackNumber)
    items = map(lambda f: os.path.join(directory, f), items)
    
    return items


class RadioPlayer(QLabel):
    
    def __init__(self, stationName, url):
        
        self.url = url
        
        QLabel.__init__(self, QString("<b>Playing " + stationName + " ('q' to quit)</b>"))
        
        self.setFont(QFont("Helvetica", 24))
        
        return
    
    def play(self): self.mplayer = pexpect.spawn('mplayer -ao alsa -quiet ' + self.url)
    
    def keyPressEvent(self, event):
        
        if event.key() == Qt.Key_Q: self.quit()           
        else: QLabel.keyPressEvent(self, event)
        
        return
    
    def quit(self):
        
        if self.mplayer != None: self.mplayer.close()
        qApp.quit()
        return
    
    pass

def do_radio(radioFilePath):
    
    with open(radioFilePath, 'r') as f: url = f.readline().strip()
    
    radioPlayer = RadioPlayer(os.path.splitext(os.path.basename(radioFilePath))[0], url );
    
    radioPlayer.setWindowTitle("Playing Internet radio...")
    
    app.connect(qApp, SIGNAL("lastWindowClosed()"), radioPlayer.quit)
    
    radioPlayer.show()
    
    radioPlayer.play()
    
    return app.exec_()


def do_album_play(albumDirPath):
    
    os.chdir(albumDirPath)
    
    # figure out what we/mplayer will be playing in a series of playlists
    
    playLists = []
    
    for d in [os.getcwd()] + sortMusicItemsInDir(os.getcwd(), "dirs"):
        
        tracks = sortMusicItemsInDir(d, "files")
        
        playLists.append(PlayList(d, tracks, d == os.getcwd()))
        pass
    
    if filter(lambda pl: len(pl.tracks) > 0, playLists) == []:
        
        QMessageBox.critical(None, "Music player","Couldn't find any tracks to play! Quitting.")
        sys.exit(2)
        pass
    
    
    # setup the GUI
    
    
    win = QWidget(None);
    
    win.setWindowTitle("Playing album...")
    
    winLayout = QVBoxLayout()
    
    #helpStr = "[space] / up / down / left / right / r / q"
    helpStr = "[space] / up / down / r / q"
    
    pausedLabel = QLabel("")
    pausedLabel.setAlignment(Qt.AlignHCenter)
    repeatModeLabel = QLabel("")
    repeatModeLabel.setAlignment(Qt.AlignHCenter)
    
    albumPlayer = AlbumPlayer(playLists, pausedLabel, repeatModeLabel)
    
    win.setFocusProxy(albumPlayer)
    win.connect(qApp, SIGNAL("lastWindowClosed()"), albumPlayer.quit)
    
    winLayout.addWidget(QLabel(QString("<b>%s<\/b>"%os.path.basename(albumDirPath.rstrip('/')))))
    winLayout.addWidget(albumPlayer)
    winLayout.addWidget(pausedLabel)
    winLayout.addWidget(repeatModeLabel)
    winLayout.addWidget(QLabel(helpStr))
    
    win.setLayout(winLayout)
    win.show()        
    
    return app.exec_()


def main():
    
    global app
    global removeLockFileUponExiting
    
    app = QApplication(sys.argv)
    
    # test and possibly create lockfile (to prevent multiple instances from running simultaneously)
    
    if os.path.exists(lockFilePath): 
        
        QMessageBox.critical(None, "Music player","Another instance of mp is already running!")
        removeLockFileUponExiting = False
        sys.exit(2)
        
    else: 
        
        with open(lockFilePath, "w"): pass
        pass
    
    
    # move into album/dir to play
    
    if len(sys.argv) != 2:
        
        print "wrong number of args!"
        print "usage: %s name_of_album_dir OR name_of_radio_file.radio"%sys.argv[0]
        sys.exit(1)
        
    elif os.path.isfile(sys.argv[1]) and sys.argv[1].endswith('.radio'): do_radio(sys.argv[1])
    
    elif os.path.isdir(sys.argv[1]): do_album_play(sys.argv[1])
    
    else: 
        
        print "bad arg!"
        sys.exit(1)
        pass
    
    return


try: main()

finally:
    
    try: os.unlink(fifoPath)
    except OSError: pass
    
    if removeLockFileUponExiting: 
        
        try: os.unlink(lockFilePath)
        except OSError: pass
        
        pass
    pass

# useful cmds to implement
# seek <value> [type]
# Seek to some place in the movie.
#  0 is a relative seek of +/- <value> seconds (default).
#  1 is a seek to <value> % in the movie.
#  2 is a seek to an absolute position of <value> seconds.
