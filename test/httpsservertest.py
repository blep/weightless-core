# -*- coding: utf-8 -*-
## begin license ##
#
#    Weightless is a High Performance Asynchronous Networking Library
#    Copyright (C) 2006-2009 Seek You Too (CQ2) http://www.cq2.nl
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

from unittest import TestCase
from random import randint

from weightless import Reactor, HttpsServer

from OpenSSL import SSL
from subprocess import Popen, PIPE

class HttpsServerTest(TestCase):

    def setUp(self):
        self.reactor = Reactor()

    def tearDown(self):
        self.reactor.shutdown()
        self.reactor = None

    def testConnect(self):
        self.req = False
        serverResponse = 'Hello World'
        def onRequest(**kwargs):
            yield 'HTTP/1.0 200 OK\r\n\r\n' + serverResponse
            self.req = True

        port = randint(15000, 16000)
        reactor = Reactor()
        server = HttpsServer(reactor, port, onRequest, keyfile='ssl/server.pkey', certfile='ssl/server.cert')

        p = Popen('wget -O - --no-check-certificate --quiet https://localhost:%s' % port, shell=True, stdout=PIPE)

        popenStdout = []
        def readPopenStdout():
            popenStdout.append(p.stdout.read())
        reactor.addReader(p.stdout, readPopenStdout)

        while not self.req:
           reactor.step()

        reactor.step()
        self.assertEquals(1, len(popenStdout))
        self.assertEquals(serverResponse, popenStdout[0])