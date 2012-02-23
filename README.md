# RP

RP.py is a micro Radio Paradise Player library.

It has two interfaces:

- **RP**, a cli interface with an OSD (based on pynotify/libnotify)
- **qRP**, a Qt interface with a bit more tricks, like history and full size covers. (based on PyQt/PySide)

It relies on python-gstreamer and has an mplayer fallback mode if your gstreamer to old.

RP is licensed under GPLv3+.

Author: Anisse Astier <anisse@astier.eu>

## History

I like to listen to Radio Paradise. A lot. I used to launch Amarok just to listen to this webradio. Then, tired of Amarok's footprint, I started using mplayer. A simple wget of the playlist then mplayer `cat rp*`. This was enough for some time.
Until I wanted to know what I was listening to. And _see_ those cover arts that kept taunting me in the ICY Info. Also, at about the same time, I discovered that pynotify was pretty nice and could do neat tricks with minimum amount of code.

That's how RP was born.

The rest is (in the git) history ;-)

