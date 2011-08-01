import os, user

# GUI/INTERFACE-RELATED config vars ###########################################

MAX_RESULTS = 200 # maximum number of search results to list (by default). Set to None to always list all matching docs

runInFullScreenMode = False

ExtensionsWidgetClassToUse = "DefaultExtensionsWidget" # "MusicExtensionsWidget" # defines the class to be used for setting the filename extension filter of the search results. MUST BE THE NAME (A STRING) OF THE CLASS (or have value None). Currently supported values: "DefaultExtensionsWidget" (lineedit-based), "MusicExtensionsWidget" (album dir vs ".radio" file) or None (no support for extension-filtering).

nameOfItem = "doc" # (or, eg, "album" to operate on a repository of music album dirs). Is used just to define the labels in the GUI

searchWindowTitle = "Find doc" # (or, eg, "Choose music"). Is used just to define the title of the do_search() window

leaveButtonCaption = "&Leave" # (or, eg, "Switch &off").  Is used just to define the title of the do_search() window. SHOULD INCLUDE '&' for keyboard-shortcut.


# IMPORTANT NON-GUI CONFIG VARS ##########################################

# By default, the next two vars are True and False, respectively. 
# To use oyepa to manage my music collection, I toggle their values.

extensionlessDirsAlwaysMatch = True # determines whether directory-docs (ie, docs which are a directory) lacking an extension match any search independently of the user having specified a filter of filename extensions

includeWordsInPurenameAsTags = False # determines whether words (len>=3chars) found in the name of a document are indexed as tags. Notice that these words are always tested to see if they match the user-selected tags/keywords; this setting only affects if they are listed in the "suggested tags" listwidget

TERMINAL_HACK = "termhack" # name of a "virtual app" (meaning, this should simply be a string which makes sense to describe the act of "opening a terminal inside a dir-doc"; need NOT be the name of a program) which the user can run on docs which are dirs ("dir-docs"). When the user enters this app name, we simply chdir into that dir-doc and run the app TERMINAL_APP (defined below)

TERMINAL_APP = "xterm" # actual name of program to execute inside a dir-doc when performing a TERMINAL_HACK; this MUST be just the program name  (no args/command line options)

FILENAMES_TO_IGNORE = ["lost+found"] # this is a list of filenames which, if found in a doc-dir, will be ignored

SORT_RESULTS_BY = "timestamp" # defines the sort criterion for the list of matching docs. Admissible values: "timestamp", "name"

TIMESTAMP_TO_USE = "mtime" # defines the timestamp which is used as the 'date' of a doc. If SORT_BY=="timestamp", then this option gains importance since it will be based on this timestamp that sorting of the matching docs will be performed. Admissible values: "atime" or "mtime". ("ctime" is ok, too, but not useful.)

MAX_FILENAME_LEN = 255

EDITOR_CMD_FOR_WNOTE = "xjed" # this is the text editor used by the 'applet' wnote.py to open/edit text notes. If you want to use a CLI editor, set this to "xterm -e name_of_editor"

NOTES_DIR_FOR_WNOTE = "notes" # this is the name of the dir (relative to the user's home dir) in which the 'applet' wnote.py will place notes

DONT_QUIT_INSTEAD_EXECUTE_CMD = None # if a string, then when the user presses the leave/quit button oyepa will NOT quit but instead pass this string to the shell for execution. Useful when acting a music jukebox to hibernate the machine rather than quit the application.

# UNIMPORTANT CONFIG VARS

OYEPA_PERSONAL_DIR = os.path.join(user.home, '.oyepa')

if not os.path.exists(OYEPA_PERSONAL_DIR): os.mkdir(OYEPA_PERSONAL_DIR)

UNTITLED_FILENAME_FOR_WNOTE = "new-note.note" # this is the filename given to untitled notes by the 'applet' wnote.py.

APP_MEMORY_FILEPATH = os.path.join(OYEPA_PERSONAL_DIR, "apps") # this file contains two dics (stored using the 'pickle' module): the first stores ("informal" app name, app executable file) pairs, the second (extension, "informal app name").

MIME_TYPES_CACHE_FILEPATH = os.path.join(OYEPA_PERSONAL_DIR, "mimetypes_cache")

NO_SUGGESTIONS_ITEM_STR = "[no suggestions]"

MAX_SAVE_PROCESS_DURATION = 5 # period of time (in secs) after which we consider that a file created with the name of a disappeared one is a NEW file

TIMEOUT_ON_WAITING_FOR_LOCK = None # in secs (or None)

TIMEOUT_ON_WAITING_FOR_FILEMON = 2 # MUST NOT BE NONE: real potential for (GUI-level) inaction if filemon crashes/is not started

FAKE_EXTENSION_FOR_DIRS = "[directory]" # internally we set the extension of dir-docs which do not have one to this string

OYEPA_GUI_FILENAME     = "oyepa"
OYEPA_FILEMON_FILENAME = "oyepa-filemon.py"
FILEPATH_FILEMON_RUNNING = os.path.join(OYEPA_PERSONAL_DIR, ".oyepa-filemon.running")

oyepa_internal_ops_filename = os.path.join(OYEPA_PERSONAL_DIR, ".oyepa-ops")
oyepa_internal_ops_lockfilename = os.path.join(OYEPA_PERSONAL_DIR, ".oyepa-ops.lock")

pending_updates_filename = ".oyepa-updates"
pending_updates_lockfilename = ".oyepa-updates.lock"

tag_cache_filename = ".oyepa-tags-cache"
tag_cache_lockfilename = ".oyepa-tags-cache.lock"

FILENAME_LISTING_DOC_DIRS = os.path.join(OYEPA_PERSONAL_DIR, "dirs")

ICON_SIZE = 24
