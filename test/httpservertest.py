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
from socket import socket, error as SocketError
from select import select
from weightless import Reactor, HttpServer
from time import sleep
from weightless import _httpserver
from cq2utils import MATCHALL

from os.path import join, abspath, dirname
def inmydir(p):
    return join(dirname(abspath(__file__)), p)

class HttpServerTest(TestCase):

    def setUp(self):
        self.reactor = Reactor()

    def tearDown(self):
        self.reactor.shutdown()
        self.reactor = None

    def sendRequestAndReceiveResponse(self, request, recvSize=4096):
        self.responseCalled = False
        def response(**kwargs):
            yield 'The Response'
            self.responseCalled = True
        port = randint(2**10, 2**16)
        server = HttpServer(self.reactor, port, response, recvSize=recvSize)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send(request)
        while not self.responseCalled:
            self.reactor.step()
        return sok.recv(4096)

    def testConnect(self):
        self.req = False
        def onRequest(**kwargs):
            self.req = True
            yield 'nosens'
        port = randint(2**10, 2**16)
        reactor = Reactor()
        server = HttpServer(reactor, port, onRequest)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send('GET / HTTP/1.0\r\n\r\n')
        reactor.step() # connect/accept
        reactor.step() # read GET request
        reactor.step() # call onRequest for response data
        self.assertEquals(True, self.req)

    def testSendHeader(self):
        self.kwargs = None
        def response(**kwargs):
            self.kwargs = kwargs
            yield 'nosense'
        port = randint(2**10, 2**16)
        reactor = Reactor()
        server = HttpServer(reactor, port, response)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send('GET /path/here HTTP/1.0\r\nConnection: close\r\nApe-Nut: Mies\r\n\r\n')
        while not self.kwargs:
            reactor.step()
        self.assertEquals({'Body': '', 'RequestURI': '/path/here', 'HTTPVersion': '1.0', 'Method': 'GET', 'Headers': {'Connection': 'close', 'Ape-Nut': 'Mies'}, 'Client': ('127.0.0.1', MATCHALL)}, self.kwargs)

    def testGetResponse(self):
        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nConnection: close\r\nApe-Nut: Mies\r\n\r\n')
        self.assertEquals('The Response', response)

    def testCloseConnection(self):
        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nConnection: close\r\nApe-Nut: Mies\r\n\r\n')
        self.assertEquals('The Response', response)
        self.assertEquals(1, len(self.reactor._readers)) # only acceptor left
        self.assertEquals({}, self.reactor._writers)

    def testSmallFragments(self):
        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nConnection: close\r\nApe-Nut: Mies\r\n\r\n', recvSize=3)
        self.assertEquals('The Response', response)

    def testSmallFragmentsWhileSendingResponse(self):

        def response(**kwargs):
            yield 'some text that is longer than '
            yield 'the lenght of fragments sent'
        port = randint(2**10, 2**16)
        reactor = Reactor()
        server = HttpServer(reactor, port, response, recvSize=3)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send('GET /path/here HTTP/1.0\r\nConnection: close\r\nApe-Nut: Mies\r\n\r\n')
        while not reactor._writers:
            reactor.step()
        serverSok, handler = reactor._writers.items()[0]
        originalSend = serverSok.send
        def sendOnlyManagesToActuallySendThreeBytesPerSendCall(data, *options):
            originalSend(data[:3], *options)
            return 3
        serverSok.send = sendOnlyManagesToActuallySendThreeBytesPerSendCall
        for i in range(21):
            reactor.step()
        fragment = sok.recv(4096)
        self.assertEquals('some text that is longer than the lenght of fragments sent', fragment)

    def testInvalidRequestStartsOnlyOneTimer(self):
        _httpserver.RECVSIZE = 3
        port = randint(2**10, 2**16)
        reactor = Reactor()
        timers = []
        orgAddTimer = reactor.addTimer
        def addTimerInterceptor(*timer):
            timers.append(timer)
            return orgAddTimer(*timer)
        reactor.addTimer = addTimerInterceptor
        server = HttpServer(reactor, port, None, timeout=0.01)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send('GET HTTP/1.0\r\n\r\n') # no path
        while select([sok],[], [], 0) != ([sok], [], []):
            reactor.step()
        response = sok.recv(4096)
        self.assertEquals('HTTP/1.0 400 Bad Request\r\n\r\n', response)
        self.assertEquals(1, len(timers))

    def testValidRequestResetsTimer(self):
        port = randint(2**10, 2**16)
        reactor = Reactor()
        server = HttpServer(reactor, port, lambda **kwargs: ('a' for a in range(3)), timeout=0.01, recvSize=3)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send('GET / HTTP/1.0\r\n\r\n')
        sleep(0.02)
        for i in range(11):
            reactor.step()
        response = sok.recv(4096)
        self.assertEquals('aaa', response)

    def testPostMethodReadsBody(self):
        self.requestData = None
        def handler(**kwargs):
            self.requestData = kwargs

        port = randint(20000,25000)
        reactor = Reactor()
        server = HttpServer(reactor, port, handler, timeout=0.01)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send('POST / HTTP/1.0\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: 8\r\n\r\nbodydata')

        while not self.requestData:
            reactor.step()
        self.assertEquals(dict, type(self.requestData))
        self.assertTrue('Headers' in self.requestData)
        headers = self.requestData['Headers']
        self.assertEquals('POST', self.requestData['Method'])
        self.assertEquals('application/x-www-form-urlencoded', headers['Content-Type'])
        self.assertEquals(8, int(headers['Content-Length']))

        self.assertTrue('Body' in self.requestData)
        self.assertEquals('bodydata', self.requestData['Body'])

    def testPostMethodTimesOutOnBadBody(self):
        self.requestData = None
        def handler(**kwargs):
            self.requestData = kwargs

        done = []
        def onDone():
            fromServer = sok.recv(1024)
            self.assertTrue('HTTP/1.0 400 Bad Request' in fromServer)
            done.append(True)

        port = randint(20000,25000)
        reactor = Reactor()
        server = HttpServer(reactor, port, handler, timeout=0.01)
        reactor.addTimer(0.02, onDone)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send('POST / HTTP/1.0\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: 8\r\n\r\n')

        while not done:
            reactor.step()


    def testReadChunkedPost(self):
        self.requestData = {}
        def handler(**kwargs):
            self.requestData = kwargs

        port = randint(20000,25000)
        reactor = Reactor()
        server = HttpServer(reactor, port, handler, timeout=0.01, recvSize=3)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send('POST / HTTP/1.0\r\nContent-Type: application/x-www-form-urlencoded\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nabcde\r\n5\r\nfghij\r\n0\r\n')

        reactor.addTimer(0.2, lambda: self.fail("Test Stuck"))
        while self.requestData.get('Body', None) != 'abcdefghij':
            reactor.step()

    def testPostMultipartForm(self):
        httpRequest = open(inmydir('data/multipart-data-01')).read()
        self.requestData = {}
        def handler(**kwargs):
            self.requestData = kwargs

        port = randint(20000,25000)
        reactor = Reactor()
        server = HttpServer(reactor, port, handler)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send(httpRequest)

        reactor.addTimer(2, lambda: self.fail("Test Stuck"))
        while self.requestData.get('Form', None) == None:
            reactor.step()
        form = self.requestData['Form']
        self.assertEquals(4, len(form))
        self.assertEquals(['SOME ID'], form['id'])

    def testWindowsPostMultipartForm(self):
        httpRequest = open(inmydir('data/multipart-data-02')).read()
        self.requestData = {}
        def handler(**kwargs):
            self.requestData = kwargs

        port = randint(20000,25000)
        reactor = Reactor()
        server = HttpServer(reactor, port, handler)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send(httpRequest)

        reactor.addTimer(2, lambda: self.fail("Test Stuck"))
        while self.requestData.get('Form', None) == None:
            reactor.step()
        form = self.requestData['Form']
        self.assertEquals(4, len(form))
        self.assertEquals(['SOME ID'], form['id'])
        self.assertEquals(1, len(form['somename']))
        filename, mimetype, data = form['somename'][0]
        self.assertEquals('Bank Gothic Medium BT.ttf', filename)
        self.assertEquals('application/octet-stream', mimetype)

    def testTextFileSeenAsFile(self):
        httpRequest = open(inmydir('data/multipart-data-03')).read()
        self.requestData = {}
        def handler(**kwargs):
            self.requestData = kwargs

        port = randint(20000,25000)
        reactor = Reactor()
        server = HttpServer(reactor, port, handler)
        sok = socket()
        sok.connect(('localhost', port))
        sok.send(httpRequest)

        reactor.addTimer(2, lambda: self.fail("Test Stuck"))
        while self.requestData.get('Form', None) == None:
            reactor.step()
        form = self.requestData['Form']
        self.assertEquals(4, len(form))
        self.assertEquals(['SOME ID'], form['id'])
        self.assertEquals(1, len(form['somename']))
        filename, mimetype, data = form['somename'][0]
        self.assertEquals('hello.bas', filename)
        self.assertEquals('text/plain', mimetype)


    #def testUncaughtException(self):
        #done = []
        #def onRequest(**kwargs):
            #yield "HTTP\1.0 200 Ok\r\n\r\nStart data"
            #done.append('onRequest')
            #raise Exception("This exception is printed.")
        #port = randint(10000, 2**16)
        #reactor = Reactor()
        #server = HttpServer(reactor, port, onRequest)
        #sok = socket()
        #sok.connect(('localhost', port))
        #sok.send('GET / HTTP/1.0\r\n\r\n')
        #reactor.addTimer(0.2, lambda: self.fail("Test Stuck"))
        #while not done:
            #reactor.step()

        #try:
            #sok.recv(4000) # wie een beter plan heeft mag het zeggen
            #self.fail('Socket not closed by server')
        #except SocketError, e:
            #print "asdf", type(e), str(e)

        ## 1. socket closed
        ## 2. exceptie geraised (print or whatever)



    #def testPrematureClientClose(self):
        """Seen in certain phases of the moon. Kvs has not (20071101) been able to reproduce this in tests."""
        #self.almostDone = False
        #self.done = False

        #def handler(**kwargs):
            #if self.almostDone == True:
                #self.done = True
                #raise StopIteration()
            #if kwargs.get("Body", None) == 'abcde':
                #self.almostDone = True

        #port = randint(20000,25000)
        #reactor = Reactor()
        #server = HttpServer(reactor, port, handler, timeout=0.01)
        #sok = socket()
        #sok.connect(('localhost', port))
        #sok.send('POST / HTTP/1.0\r\nContent-Type: application/x-www-form-urlencoded\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nabcde\r\n0\r\n')

        #reactor.addTimer(0.2, lambda: self.fail("Test Stuck"))
        #while not self.done:
            #reactor.step()
