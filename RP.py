#!/usr/bin/env python
# coding: utf-8
# RP, a micro Radio Paradise Player
#
# - Ctrl+C to exit
#
# Author: Anisse Astier <anisse@astier.eu>


# Python 3 compatibility
# XXX: Useless with gstreamer :-(((
from __future__ import print_function
import sys
PYTHON3 = sys.version_info >= (3, 0)
if PYTHON3:
    b = lambda s : str(s, encoding='utf8') # buffer(urlopen, file reading) conversion to strings for parsing
    from urllib.request import urlopen
else:
    b = lambda s : s
    from urllib2 import urlopen

import tempfile
import os
import posixpath # for URL manipulation
import time
import subprocess
from pkg_resources import parse_version

import gobject, pygst
pygst.require("0.10")
import gst

# This should be an abstract base class (abc)
# anyway, using it will fail because self.imgpath is not defined
class _CoverFetcher:
    def __init__(self, sizepreference=None):
        #Accepted arguments 'l' (large) or 's' (small)
        if sizepreference == 'l' or sizepreference == 's':
            self.sizepref = sizepreference
        else:
            self.sizepref = None

    def get_image(self, imgurl):
        # Specially for Radio Paradise:
        # small image is enough for our cache and display purpose.
        if imgurl.find('graphics/covers/m') != -1 and self.sizepref != None:
            # we try the big image first, then the provided URL
            urlist = [imgurl.replace('graphics/covers/m', 'graphics/covers/'+self.sizepref), imgurl]
        else:
            urlist = [imgurl]
        # download image in cache
        page = None
        content = None
        for url in urlist:
            try:
                page = urlopen(url)
                content = page.read()
                if len(content) <= 807: #this is hack to skip empty 1x1 GIF files
                    page = content = None
                    continue
            except: # we *really* want to ignore any error here.
                pass
            else: # stop at the first working url
                break
        if page == None or content == None: # no working url :-(
            return None

        try:
            f = open(self.imgpath, 'wb')
            f.write(content)
            f.close()
        except: #whatever happened in file creation/writing, we just don't have any image to show
            return None
        return self.imgpath

class CachedCoverFetcher(_CoverFetcher):
    def __init__(self, cachedir, sizepref=None):
        self.coverdir = cachedir + '/covers'
        if not os.path.isdir(self.coverdir):
            os.makedirs(self.coverdir) # we expect OSError to be thrown to caller in case of failure
        _CoverFetcher.__init__(self, sizepref)

    def get_image(self, imgurl):
        # get basename
        self.imgpath = self.coverdir + '/' + posixpath.basename(imgurl)
        # check if it's in the cache
        if os.path.exists(self.imgpath):
            return self.imgpath

        return _CoverFetcher.get_image(self, imgurl)

class TmpCoverFetcher(_CoverFetcher):
    def __init__(self, sizepref=None):
        tmpfile = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        tmpfile.close()
        self.imgpath = tmpfile.name
        _CoverFetcher.__init__(self, sizepref)

    def __del__(self):
        if os.path.exists(self.imgpath):
            os.unlink(self.imgpath)

class GstreamerBackend:
    def __init__(self, update_cb, eos_cb):
        # before constructing gstreamer pipeline, check if we have the required
        # icydemux version to get images in the "homepage" tag
        icydemux_version = gst.registry_get_default().find_plugin("icydemux").get_version()
        # feature we want was added in version 0.10.27, commit be2d04e040aa3a6fb556f660fbfa624d32a3f017
        if parse_version(icydemux_version) < parse_version("0.10.27"):
            raise RuntimeError("Your gstreamer version is too old to get cover art")

        self.update_cb = update_cb
        self.eos_cb = eos_cb

        self.player = gst.element_factory_make("playbin2", "player")
        self.bus = self.player.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self._on_message)
        gobject.threads_init()

    def __del__(self):
        if hasattr(self, "bus"):
            self.bus.remove_signal_watch()

    def _on_message(self, bus, message):
        t = message.type
        artist = song = coverurl = None
        update = False
        if t == gst.MESSAGE_ERROR:
            print(message.parse_error())
            self.player.set_state(gst.STATE_NULL)

        elif t == gst.MESSAGE_EOS:
            self.eos_cb()

        elif t == gst.MESSAGE_TAG:
            tags =  message.parse_tag()
            for tag in tags.keys():
                if tag == 'title':
                    artist,song = tags[tag].split(" - ", 1)
                    update = True
                elif tag == 'homepage':
                    coverurl = tags[tag]
                    update = True
        if update == True:
            print("%s - %s"%(artist,song))
            self.update_cb(artist, song, coverurl)

    # Go onto next playlist element or quit if we reached the end
    def play(self, uri):
        self.player.set_property("uri", uri)
        self.player.set_state(gst.STATE_PLAYING)

class MplayerBackend:
    def __init__(self, update_cb, eos_cb):
        self.update_cb = update_cb
        self.eos_cb = eos_cb

        self.cmd = ['mplayer', '-vo', 'null', '-quiet', '-softvol']

    def _parse_icyinfo(self, icystring):
        #parsing sample:
        # ICY Info: StreamTitle='Jimi Hendrix - The Wind Cries Mary';StreamUrl='http://www.radioparadise.com/graphics/covers/m/B000002OOG.jpg';
        if icystring.find("ICY Info: StreamTitle=") == -1:
            return None,None,None

        streamurl = artist = songname = ""
        l = icystring[len('ICY Info: '):] #remove prefix
        for tok in l.split(';'):
            if len(tok) < 2: # remove strings that are empty or non-matching
                continue
            tokname,tokvalue = tok.split('=', 1)
            if tokname == "StreamTitle":
                song = tokvalue.strip("'")
                artist,songname = song.split(" - ", 1)
            elif tokname == "StreamUrl":
                    streamurl = tokvalue.strip("'")
        return artist,songname,streamurl

    #TODO:
    # - fix semantics of the play() call. This backend should really be in a separate thread in order to be on par with the gstreamer backend, and allow this function to return once it's started. Also, this breaks the qRP UI
    # - allow support of multiple playlist elements
    def play(self, uri):
        try:
            p = subprocess.Popen(self.cmd + [uri], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except:
            print("Unable to run mplayer. Do you have it installed on your system ?")
            sys.exit(1)
        while p.poll() == None:
            try:
                l = p.stdout.readline()
                artist,song,coverurl = self._parse_icyinfo(b(l))
                if artist == song == coverurl == None:
                    continue
                print("%s - %s"%(artist,song))
                self.update_cb(artist, song, coverurl)
            except KeyboardInterrupt:
                p.terminate()
        sys.exit(1)

class Player:
    def __init__(self, playlisturl, sizepref=None):
        self.playlist = [ i.strip()
                for i in b(urlopen(playlisturl).read()).split('\n')
                    if len(i) > 1 and i[0] != '#'] #TODO: check for urlopen errors

        try:
            self.backend = GstreamerBackend(self._now_playing, self._next)
        except:
            self.backend = MplayerBackend(self._now_playing, self._next)

        cachedir = os.getenv("XDG_CACHE_HOME", "~/.cache")
        self.cache_dir = os.path.expanduser(cachedir+"/RP")
        try:
            self.fetcher = CachedCoverFetcher(self.cache_dir, sizepref)
        except:
            self.fetcher = TmpCoverFetcher(sizepref)

        datahome = os.getenv("XDG_DATA_HOME", "~/.local/share")
        if not os.path.isdir(datahome + "/RP"):
            os.makedirs(datahome + "/RP") # we expect OSError to be thrown to caller in case of failure
        self.logfile = os.path.expanduser(datahome + "/RP/log")

    def _now_playing(self, artist, song, imgurl):
        # Log everything that is played
        if imgurl != None: #only if we have an image
            log = open(self.logfile, 'a')
            log.write('"%s","%s","%s","%s"\n' %
                    (time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                        imgurl,artist,song))
            log.close()

        # Update text while we wait for image to load
        self.show_current_preview(artist, song)
        if imgurl != None:
            imgpath = self.fetcher.get_image(imgurl)
        else:
            imgpath = None
        self.show_current(artist, song, imgpath)

    # Go onto next playlist element or quit if we reached the end
    def _next(self):
        self.currentplaylistitem += 1
        if self.currentplaylistitem >= len(self.playlist):
            sys.exit(0)
        self.backend.play(self.playlist[self.currentplaylistitem])

    def play(self):
        self.currentplaylistitem = 0
        self.backend.play(self.playlist[self.currentplaylistitem])


#TODO:
# - keep playlist in a cache (then randomize order for load-balancing)
# - Add a setup.py to allow installation and python packaging
# - Different storage for different sizes
# - Bring back Python 3 support with pygi

def show_current(*args):
    pass

def show_current_preview(*args):
    pass

def main():
    player = Player("http://www.radioparadise.com/musiclinks/rp_128aac.m3u")
    player.show_current = show_current
    player.show_current_preview = show_current_preview
    player.play()
    import glib
    loop = glib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\n")
        sys.exit(0)


if __name__ == '__main__':
    main()
