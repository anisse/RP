#!/usr/bin/env python
# coding: utf-8
# RP, a micro Radio Paradise Player
# Relies on python-gstreamer + libnotify for OSD
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
from pkg_resources import parse_version

import gobject, pygst
pygst.require("0.10")
import gst

# This should be an abstract base class (abc)
# anyway, using it will fail because self.imgpath is not defined
class CoverFetcher:
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

class CachedCoverFetcher(CoverFetcher):
    def __init__(self, cachedir, sizepref=None):
        self.coverdir = cachedir + '/covers'
        if not os.path.isdir(self.coverdir):
            os.makedirs(self.coverdir) # we expect OSError to be thrown to caller in case of failure
        CoverFetcher.__init__(self, sizepref)

    def get_image(self, imgurl):
        # get basename
        self.imgpath = self.coverdir + '/' + posixpath.basename(imgurl)
        # check if it's in the cache
        if os.path.exists(self.imgpath):
            return self.imgpath

        return CoverFetcher.get_image(self, imgurl)

class TmpCoverFetcher(CoverFetcher):
    def __init__(self, sizepref=None):
        tmpfile = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        tmpfile.close()
        self.imgpath = tmpfile.name
        CoverFetcher.__init__(self, sizepref)

    def __del__(self):
        if os.path.exists(self.imgpath):
            os.unlink(self.imgpath)

class Player:
    def __init__(self, playlisturl, sizepref=None):
        self.playlist = b(urlopen(playlisturl).read()).split('\n') #TODO: check for errors

        # before constructing gstreamer pipeline, check if we have the required
        # icydemux version to get images in the "homepage" tag
        icydemux_version = gst.registry_get_default().find_plugin("icydemux").get_version()
        # feature we want was added in version 0.10.27, commit be2d04e040aa3a6fb556f660fbfa624d32a3f017
        if parse_version(icydemux_version) < parse_version("0.10.27"):
            raise RuntimeError("Your gstreamer version is too old to get cover art")
        self.player = gst.element_factory_make("playbin2", "player")
        self.bus = self.player.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)
        gobject.threads_init()

        self.cache_dir = os.path.expanduser('~/.config/RP/cache')
        try:
            self.fetcher = CachedCoverFetcher(self.cache_dir, sizepref)
        except:
            self.fetcher = TmpCoverFetcher(sizepref)

    def __del__(self):
        if hasattr(self, "bus"):
            self.bus.remove_signal_watch()

    def _now_playing(self, artist, song, imgurl):
        # Log everything that is played
        if imgurl != None: #only if we have an image
            log = open(self.cache_dir + '/log', 'a')
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

    def on_message(self, bus, message):
        t = message.type
        artist = song = coverurl = None
        update = False
        if t == gst.MESSAGE_ERROR:
            print(message.parse_error())
            self.player.set_state(gst.STATE_NULL)

        elif t == gst.MESSAGE_EOS:
            self._next()

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
            self._now_playing(artist, song, coverurl)

    # Go onto next playlist element or quit if we reached the end
    def _next(self):
        self.currentplaylistitem += 1
        if self.currentplaylistitem >= len(self.playlist):
            sys.exit(0)
        self.player.set_property("uri", self.playlist[self.currentplaylistitem])
        self.player.set_state(gst.STATE_PLAYING)

    def play(self):
        self.currentplaylistitem = 0
        self.player.set_property("uri", self.playlist[self.currentplaylistitem])
        self.player.set_state(gst.STATE_PLAYING)



#TODO:
# - keep playlist in a cache (then randomize order for load-balancing)
# - Add a setup.py to allow installation and python packaging

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
