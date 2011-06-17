#!/usr/bin/env python

# Reference:
# http://pygstdocs.berlios.de/pygst-tutorial/playbin.html
import gobject, glib
import pygst
pygst.require("0.10")
import gst


class Main:
    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_TAG:
            tags =  message.parse_tag()
            for tag in tags.keys():
                if tag == 'title' or tag == 'homepage':
                    print tags[tag]

    def __init__(self):
        self.player = gst.element_factory_make("playbin2", "player")
        self.bus = self.player.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)

    def __del__(self):
        bus.remove_signal_watch()

    def start(self):
        self.player.set_property("uri", "http://scfire-ntc-aa03.stream.aol.com:80/stream/1049")
        self.player.set_state(gst.STATE_PLAYING)


main = Main()
gobject.threads_init()
loop = glib.MainLoop()
main.start()
try:
    loop.run()
except:
    print "bla"

