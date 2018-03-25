# not very good with gui development...
# don't read this file, it sucks

import signal
import subprocess
import webbrowser
from sys import argv, exit, executable, platform, version_info, maxsize
from os import kill, rmdir
from os.path import isfile, isdir
from time import sleep
from traceback import print_exception

from appJar import gui

import __init__ as init
from pyctr.util import config_dirs

b9_paths = ('boot9.bin', 'boot9_prot.bin',
            config_dirs[0] + '/boot9.bin', config_dirs[0] + '/boot9_prot.bin',
            config_dirs[1] + '/boot9.bin', config_dirs[1] + '/boot9_prot.bin')

seeddb_paths = ('seeddb.bin', config_dirs[0] + '/seeddb.bin', config_dirs[1] + '/seeddb.bin')

for p in b9_paths:
    if isfile(p):
        b9_found = True
        break
else:
    b9_found = False

for p in seeddb_paths:
    if isfile(p):
        seeddb_found = True
        break
else:
    seeddb_found = False

# types
CCI = 'CTR Cart Image (".3ds", ".cci")'
CDN = 'CDN contents'
CIA = 'CTR Importable Archive (".cia")'
EXEFS = 'Executable Filesystem (".exefs", "exefs.bin")'
NAND = 'NAND backup ("nand.bin")'
NCCH = 'NCCH (".cxi", ".cfa", ".ncch", ".app")'
ROMFS = 'Read-only Filesystem (".romfs", "romfs.bin")'
SD = 'SD Card Contents ("Nintendo 3DS" from an SD card)'
TITLEDIR = 'Titles directory ("title" from NAND or SD)'

mount_types = {CCI: 'cci', CDN: 'cdn', CIA: 'cia', EXEFS: 'exefs', NAND: 'nand', NCCH: 'ncch', ROMFS: 'romfs', SD: 'sd',
               TITLEDIR: 'titledir'}

types_list = (CCI, CDN, CIA, EXEFS, NAND, NCCH, ROMFS, SD, TITLEDIR)

windows = platform == 'win32'  # only for native windows, not cygwin
macos = platform == 'darwin'

if windows:
    from ctypes import windll
    from os import startfile
    from string import ascii_uppercase
    from sys import stdout

    # unlikely, but this causes issues
    if stdout is None:  # happens if pythonw is used on windows
        res = windll.user32.MessageBoxW(None, (
            'This is being run with the wrong Python executable.\n'
            'This should be installed as a module, then run using the py launcher on Python 3.5.2 or later.\n\n'
            'Click OK to open the fuse-3ds repository on GitHub:\n'
            'https://github.com/ihaveamac/fuse-3ds'),
            'fuse-3ds', 0x00000010 | 0x00000001)
        if res == 1:
            webbrowser.open('https://github.com/ihaveamac/fuse-3ds')
        exit(1)

    # https://stackoverflow.com/questions/827371/is-there-a-way-to-list-all-the-available-drive-letters-in-python
    def get_unused_drives():
        drives = []
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in ascii_uppercase:
            if not bitmask & 1:
                drives.append(letter)
            bitmask >>= 1

        return drives

    def update_drives():
        app.changeOptionBox('mountpoint', (x + ':' for x in get_unused_drives()))

_used_pyinstaller = False
process = None  # type: subprocess.Popen
curr_mountpoint = None  # type: str

app = gui('fuse-3ds ' + init.__version__, showIcon=False)

def run_mount(module_type: str, item: str, mountpoint: str, extra_args: list = ()):
    global process, curr_mountpoint
    if process is None or process.poll() is not None:
        args = [executable]
        if not _used_pyinstaller:
            args.append('-mfuse3ds')
        args.extend((module_type, '-f', item, mountpoint))
        args.extend(extra_args)
        curr_mountpoint = mountpoint
        print('Running:', args)
        opts = {}
        if windows:
            opts['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(args, **opts)
        process.wait(3)


def stop_mount():
    global process
    if process is not None and process.poll() is None:
        print('Stopping')
        if windows:
            kill(process.pid, signal.CTRL_BREAK_EVENT)
        else:
            # this is cheating...
            if platform == 'darwin':
                subprocess.check_call(['diskutil', 'unmount', curr_mountpoint])
            else:
                # assuming linux or bsd, which have fusermount
                subprocess.check_call(['fusermount', '-u', curr_mountpoint])


def press(button: str):
    if button == 'Mount':
        extra_args = []
        mount_type = app.getOptionBox('TYPE')
        app.disableButton('Mount')
        item = app.getEntry(mount_type + 'item')

        if windows:
            if app.getRadioButton('mountpoint-choice') == 'Drive letter':
                mountpoint = app.getOptionBox('mountpoint')
            else:
                mountpoint = app.getEntry('mountpoint')
                try:
                    # winfsp won't work on an existing directory
                    # so we try to use rmdir, which will delete it, only if it's empty
                    rmdir(mountpoint)
                except FileNotFoundError:
                    pass
                except Exception as e:
                    if isinstance(e, OSError) and e.winerror == 145:  # "The directory is not empty"
                        app.showSubWindow('mounterror-dir-win')
                    else:
                        print_exception(type(e), e, e.__traceback__)
                        app.showSubWindow('mounterror')
                    app.enableButton('Mount')
                    return
        else:
            mountpoint = app.getEntry('mountpoint')

        if mount_type == NAND:
            otp = app.getEntry(NAND + 'otp')
            cid = app.getEntry(NAND + 'cid')
            aw = app.getCheckBox(NAND + 'aw')
            if otp:
                extra_args.extend(('--otp', otp))
            if cid:
                extra_args.extend(('--cid', cid))
            if aw:
                extra_args.append('-r')
        elif mount_type == SD:
            movable = app.getEntry(SD + 'movable')
            aw = app.getCheckBox(SD + 'aw')
            extra_args.extend(('--movable', movable))
            if not aw:
                extra_args.append('-r')

        try:
            run_mount(mount_types[mount_type], item, mountpoint, extra_args)
        except subprocess.TimeoutExpired:
            # worked! maybe! if it didn't exit after 3 seconds!
            app.enableButton('Unmount')
            if windows:
                while not isdir(mountpoint):
                    sleep(1)
                try:
                    subprocess.check_call(['explorer', mountpoint.replace('/', '\\')])
                except subprocess.CalledProcessError:
                    # not using startfile since i've been getting fatal errors (PyEval_RestoreThread) on windows
                    #   for some reason
                    pass
            return
        except Exception as e:
            print_exception(type(e), e, e.__traceback__)
        # if it didn't work...
        app.showSubWindow('mounterror')
        app.enableButton('Mount')

    elif button == 'Unmount':
        app.disableButton('Unmount')
        # noinspection PyBroadException
        try:
            stop_mount()
            app.enableButton('Mount')
        except Exception as e:
            print_exception(type(e), e, e.__traceback__)
            app.showSubWindow('unmounterror')
            app.enableButton('Unmount')
    elif button == 'GitHub repository':
        webbrowser.open('https://github.com/ihaveamac/fuse-3ds')


def kill_process(_):
    process.kill()
    app.hideSubWindow('unmounterror')
    app.enableButton('Mount')
    app.disableButton('Unmount')


def change_type(*_):
    mount_type = app.getOptionBox('TYPE')
    for t in mount_types:
        if t == mount_type:
            app.showFrame(t)
        else:
            app.hideFrame(t)
    if not b9_found and mount_type in {CCI, CDN, CIA, NAND, NCCH, SD, TITLEDIR}:
        app.disableButton('Mount')
    else:
        if process is None or process.poll() is not None:
            app.enableButton('Mount')


# TODO: SeedDB stuff
# TODO: maybe check if the mount was unmounted outside of the unmount button

with app.frame(CCI, row=1, colspan=3):
    app.addLabel(CCI + 'label1', 'File', row=0, column=0)
    app.addFileEntry(CCI + 'item', row=0, column=1)

with app.frame(CDN, row=1, colspan=3):
    app.addLabel(CDN + 'label1', 'Directory', row=0, column=0)
    app.addDirectoryEntry(CDN + 'item', row=0, column=1)
app.hideFrame(CDN)

with app.frame(CIA, row=1, colspan=3):
    app.addLabel(CIA + 'label1', 'File', row=0, column=0)
    app.addFileEntry(CIA + 'item', row=0, column=1)
app.hideFrame(CIA)

with app.frame(EXEFS, row=1, colspan=3):
    app.addLabel(EXEFS + 'label1', 'File', row=0, column=0)
    app.addFileEntry(EXEFS + 'item', row=0, column=1)
app.hideFrame(EXEFS)

with app.frame(NAND, row=1, colspan=3):
    app.addLabel(NAND + 'label1', 'File', row=0, column=0)
    app.addFileEntry(NAND + 'item', row=0, column=1)
    app.addLabel(NAND + 'label2', 'OTP file*', row=2, column=0)
    app.addFileEntry(NAND + 'otp', row=2, column=1)
    app.addLabel(NAND + 'label3', 'CID file*', row=3, column=0)
    app.addFileEntry(NAND + 'cid', row=3, column=1)
    app.addLabel(NAND + 'label4', '*Not required if backup has essential.exefs from GodMode9.', row=4, colspan=3)
    app.addLabel(NAND + 'label5', 'Allow writing', row=5, column=0)
    app.addNamedCheckBox('', NAND + 'aw', row=5, column=1)
app.hideFrame(NAND)

with app.frame(NCCH, row=1, colspan=3):
    app.addLabel(NCCH + 'label1', 'File', row=0, column=0)
    app.addFileEntry(NCCH + 'item', row=0, column=1)
app.hideFrame(NCCH)

with app.frame(ROMFS, row=1, colspan=3):
    app.addLabel(ROMFS + 'label1', 'File', row=0, column=0)
    app.addFileEntry(ROMFS + 'item', row=0, column=1)
app.hideFrame(ROMFS)

with app.frame(SD, row=1, colspan=3):
    app.addLabel(SD + 'label1', 'Directory', row=0, column=0)
    app.addDirectoryEntry(SD + 'item', row=0, column=1)
    app.addLabel(SD + 'label2', 'movable.sed', row=2, column=0)
    app.addFileEntry(SD + 'movable', row=2, column=1)
    app.addLabel(SD + 'label3', 'Allow writing', row=3, column=0)
    app.addNamedCheckBox('', SD + 'aw', row=3, column=1)
app.hideFrame(SD)

with app.frame(TITLEDIR, row=1, colspan=3):
    app.addLabel(TITLEDIR + 'label1', 'Directory', row=0, column=0)
    app.addDirectoryEntry(TITLEDIR + 'item', row=0, column=1)
app.hideFrame(TITLEDIR)

app.setSticky('new')
app.addOptionBox('TYPE', types_list, row=0, colspan=3)
app.setOptionBoxChangeFunction('TYPE', change_type)

app.setSticky('sew')
if windows:
    def rb_change(_):
        if app.getRadioButton('mountpoint-choice') == 'Drive letter':
            app.hideFrame('mountpoint-dir')
            app.showFrame('mountpoint-drive')
        else:
            app.hideFrame('mountpoint-drive')
            app.showFrame('mountpoint-dir')

    with app.frame('win-mountpoint', row=2, colspan=3):
        app.addLabel('mountpoint-choice-label', 'Mount type', row=0)
        app.addRadioButton('mountpoint-choice', "Drive letter", row=0, column=1)
        app.addRadioButton('mountpoint-choice', "Directory", row=0, column=2)
        app.setRadioButtonChangeFunction('mountpoint-choice', rb_change)
        with app.frame('mountpoint-drive', row=1, colspan=3):
            app.addLabel('mountlabel1', 'Drive letter', row=0, column=0)
            app.addOptionBox('mountpoint', ['WWWW'], row=0, column=1) # putting "WWWW" to avoid a warning
        with app.frame('mountpoint-dir', row=1, colspan=3):
            app.addLabel('mountlabel2', 'Mount point', row=0, column=0)
            app.addDirectoryEntry('mountpoint', row=0, column=1)
        app.hideFrame('mountpoint-dir')
        # noinspection PyUnboundLocalVariable
        update_drives()
else:
    app.addLabel('mountlabel', 'Mount point', row=2, column=0)
    app.addDirectoryEntry('mountpoint', row=2, column=1)

with app.frame('FOOTER', row=3, colspan=3):
    app.addButtons(['Mount', 'Unmount', 'GitHub repository'], press, colspan=3)
    app.disableButton('Unmount')
    if not b9_found:
        app.addHorizontalSeparator()
        app.addLabel('no-b9', 'boot9 was not found.\n'
                              'Please see the GitHub README for details.\n'
                              'Types that require encryption have been disabled.')
        app.setLabelBg('no-b9', '#ff9999')
        app.disableButton('Mount')
    if not seeddb_found:
        app.addHorizontalSeparator()
        app.addLabel('no-seeddb', 'SeedDB was not found.\n'
                              'Please see the GitHub README for details.\n'
                              'Titles that require seeds may fail.')
        app.setLabelBg('no-seeddb', '#ffff99')
    app.addHorizontalSeparator()
    app.addLabel('footer', 'fuse-3ds {0} running on Python {1[0]}.{1[1]}.{1[2]} {2} on {3}'.format(
        init.__version__, version_info, '64-bit' if maxsize > 0xFFFFFFFF else '32-bit', platform), colspan=3)

# app.addStatusbar()
# app.setStatusbar('Waiting')
app.setFont(10)
app.setResizable(False)

# failed to mount subwindow
with app.subWindow('mounterror', 'fuse-3ds Error', modal=True, blocking=True):
    app.addLabel('mounterror-label', 'Failed to mount. Please check the output.')
    app.addNamedButton('OK', 'mounterror-ok', lambda _: app.hideSubWindow('mounterror'))
    app.setResizable(False)

if windows:
    # failed to mount to directory subwindow
    with app.subWindow('mounterror-dir-win', 'fuse-3ds Error', modal=True, blocking=True):
        app.addLabel('mounterror-dir-label', 'Failed to mount to the given mount point.\n'
                                             'Please make sure the directory is empty or does not exist.')
        app.addNamedButton('OK', 'mounterror-dir-ok', lambda _: app.hideSubWindow('mounterror-dir-win'))
        app.setResizable(False)

# failed to unmount subwindow
with app.subWindow('unmounterror', 'fuse-3ds Error', modal=True, blocking=True):
    def unmount_ok(_):
        app.hideSubWindow('unmounterror')
        app.enableButton('Unmount')

    app.addLabel('unmounterror-label', 'Failed to unmount. Please check the output.\n\n'
                                       'You can kill the process if it is not responding.\n'
                                       'This should be used as a last resort.'
                                       'The process should be unmounted normally.', colspan=2)
    app.addNamedButton('OK', 'unmounterror-ok', unmount_ok)
    app.addNamedButton('Kill process', 'unmounterror-kill', kill_process, row='previous', column=1)
    app.setResizable(False)


def main(_pyi=False, _allow_admin=False):
    global _used_pyinstaller
    _used_pyinstaller = _pyi
    try:
        # attempt importing all the fusepy stuff used in the mount scripts
        # if it fails, libfuse probably couldn't be found
        from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
    except EnvironmentError:
        # TODO: probably check if this was really "Unable to find libfuse" (this is aliased to OSError)
        if windows:
            if _used_pyinstaller:  # the right fusepy has to be included if it's a pyinstaller exe
                res = windll.user32.MessageBoxW(None, (
                    'Failed to import fusepy. WinFsp needs to be installed.\n\n'
                    'Click OK to open the WinFsp download page:\n'
                    'http://www.secfs.net/winfsp/download/'),
                    'fuse-3ds', 0x00000010 | 0x00000001)
                if res == 1:
                    webbrowser.open('http://www.secfs.net/winfsp/download/')
            else:
                res = windll.user32.MessageBoxW(None, (
                    'Failed to import fusepy. Either WinFsp or fusepy needs to be installed.\n'
                    'Please check the README of fuse-3ds for more details.\n\n'
                    'Click OK to open the fuse-3ds repository on GitHub:\n'
                    'https://github.com/ihaveamac/fuse-3ds'),
                    'fuse-3ds', 0x00000010 | 0x00000001)
                if res == 1:
                    webbrowser.open('https://github.com/ihaveamac/fuse-3ds')
        elif macos:
            print('Failed to load fusepy. Make sure FUSE for macOS (osxfuse) is installed.\n'
                  'https://osxfuse.github.io')
        else:
            print("Failed to load fusepy. libfuse probably couldn't be found.")
        return 1

    if windows and not _allow_admin:
        if windll.shell32.IsUserAnAdmin():
            windll.user32.MessageBoxW(None, (
                'This should not be run as administrator.\n'
                'The mount point may not be accessible by your account normally,'
                'only by the administrator.\n\n'
                'If you are having issues with administrative tools not seeing files,'
                'choose a directory as a mount point instead of a drive letter.'),
                'fuse-3ds', 0x00000010)
            exit(1)

    app.go()
    stop_mount()
    return 0