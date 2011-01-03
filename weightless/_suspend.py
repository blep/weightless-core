## begin license ##
#
#    Weightless is a High Performance Asynchronous Networking Library
#    Copyright (C) 2010 Seek You Too (CQ2) http://www.cq2.nl
#
#    This file is part of Weightless
#
#    Weightless is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    Weightless is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Weightless; if not, write to the Free Software
#    Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
## end license ##
from traceback import print_exc

def extractValueForbackwardsCompatability(exc_type, exc_value, exc_traceback):
    if exc_value is None and exc_traceback is None:
        # exc_type is a exception class *instance* (old-style behaviour)
        return type(exc_type), exc_type, None
    return None

class Suspend(object):
    def __init__(self, doNext=lambda this: None):
        self._doNext = doNext
        self._exception = None

    def __call__(self, reactor, whenDone):
        self._reactor = reactor
        try:
            self._doNext(self)
        except Exception, e:
            self._exception = e
            print_exc()
        else:
            self._whenDone = whenDone
            self._handle = reactor.suspend()

    def resume(self, response=None):
        self._response = response
        self._whenDone()

    def throw(self, exc_type, exc_value=None, exc_traceback=None):
        self._exception = (exc_type, exc_value, exc_traceback)
        self._whenDone()

    def resumeWriter(self):
        if hasattr(self, "_handle"):
            self._reactor.resumeWriter(self._handle)

    def getResult(self):
        if self._exception:
            exc_tuple = extractValueForbackwardsCompatability(*self._exception) or self._exception
            raise exc_tuple[0], exc_tuple[1], exc_tuple[2]
        return self._response

