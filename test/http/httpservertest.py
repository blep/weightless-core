# -*- coding: utf-8 -*-
## begin license ##
# 
# "Weightless" is a High Performance Asynchronous Networking Library. See http://weightless.io 
# 
# Copyright (C) 2006-2011 Seek You Too (CQ2) http://www.cq2.nl
# Copyright (C) 2011-2012 Seecr (Seek You Too B.V.) http://seecr.nl
# 
# This file is part of "Weightless"
# 
# "Weightless" is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# 
# "Weightless" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with "Weightless"; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# 
## end license ##

from __future__ import with_statement

from weightlesstestcase import WeightlessTestCase, MATCHALL
from random import randint
from socket import socket, error as SocketError
from select import select
from weightless.io import Reactor
from time import sleep
from seecr.test import CallTrace
from os.path import join, abspath, dirname
from StringIO import StringIO
from sys import getdefaultencoding
from zlib import compress
from gzip import GzipFile

from weightless.http import HttpServer, _httpserver, REGEXP
from weightless.core import Yield, compose

from weightless.http._httpserver import updateResponseHeaders, parseContentEncoding, parseAcceptEncoding

def inmydir(p):
    return join(dirname(abspath(__file__)), p)

class HttpServerTest(WeightlessTestCase):

    def sendRequestAndReceiveResponse(self, request, response='The Response', recvSize=4096, compressResponse=False, extraStepAfterCompress=True):
        self.responseCalled = False
        @compose
        def responseGenFunc(**kwargs):
            yield response
            yield ''
            self.responseCalled = True
        server = HttpServer(self.reactor, self.port, responseGenFunc, recvSize=recvSize, compressResponse=compressResponse)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send(request)

        mockStdout = None
        with self.stdout_replaced() as mockStdout:
            while not self.responseCalled:
                self.reactor.step()
            if compressResponse and extraStepAfterCompress: #not everythingSent???: 
                self.reactor.step()
        stdoutValue = mockStdout.getvalue()
        if stdoutValue:
            print stdoutValue

        server.shutdown()
        r = sok.recv(4096)
        sok.close()
        return r

    def testConnect(self):
        self.req = False
        def onRequest(**kwargs):
            self.req = True
            yield 'nosens'
        reactor = Reactor()
        server = HttpServer(reactor, self.port, onRequest)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send('GET / HTTP/1.0\r\n\r\n')
        reactor.step() # connect/accept
        reactor.step() # read GET request
        reactor.step() # call onRequest for response data
        self.assertEquals(True, self.req)

    def testConnectBindAddress(self):
        reactor = CallTrace()
        server = HttpServer(reactor, self.port, lambda **kwargs: None, bindAddress='127.0.0.1')
        server.listen()
        self.assertEquals(('127.0.0.1', self.port), server._acceptor._sok.getsockname())


    def testSendHeader(self):
        self.kwargs = None
        def response(**kwargs):
            self.kwargs = kwargs
            yield 'nosense'
        reactor = Reactor()
        server = HttpServer(reactor, self.port, response)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send('GET /path/here HTTP/1.0\r\nConnection: close\r\nApe-Nut: Mies\r\n\r\n')
        while not self.kwargs:
            reactor.step()
        self.assertEquals({'Body': '', 'RequestURI': '/path/here', 'HTTPVersion': '1.0', 'Method': 'GET', 'Headers': {'Connection': 'close', 'Ape-Nut': 'Mies'}, 'Client': ('127.0.0.1', MATCHALL)}, self.kwargs)

    def testGetResponse(self):
        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nConnection: close\r\nApe-Nut: Mies\r\n\r\n')
        self.assertEquals('The Response', response)

    def testGetCompressedResponse_deflate(self):
        rawHeaders = 'HTTP/1.1 200 OK\r\n'
        rawBody = '''This is the response.
        Nicely uncompressed, and readable.'''
        rawResponse = rawHeaders + '\r\n' + rawBody
        def rawResponser():
            for c in rawResponse:
                yield Yield
                yield c
        compressedResponse = rawHeaders + 'Content-Encoding: deflate\r\n\r\n' + compress(rawBody)
        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nAccept-Encoding: deflate\r\n\r\n', response=rawResponser(), compressResponse=True)
        self.assertEquals(compressedResponse, response)

    def testGetCompressedResponse_deflate_ContentLengthStripped(self):
        rawHeaders = 'HTTP/1.1 200 OK\r\nSome: Header\r\nContent-Length: 12345\r\nAnother: Header\r\n'
        rawBody = '''This is the response.
        Nicely uncompressed, and readable.'''
        rawResponse = rawHeaders + '\r\n' + rawBody
        def rawResponser():
            for c in rawResponse:
                yield Yield
                yield c
        compressedResponse = rawHeaders.replace('Content-Length: 12345\r\n', '') + 'Content-Encoding: deflate\r\n\r\n' + compress(rawBody)
        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nAccept-Encoding: deflate\r\n\r\n', response=rawResponser(), compressResponse=True)
        self.assertEquals(compressedResponse, response)

    def testGetCompressedResponse_gzip_ContentLengthStripped(self):
        rawHeaders = 'HTTP/1.1 200 OK\r\nSome: Header\r\nContent-Length: 12345\r\nAnother: Header\r\n'
        rawBody = '''This is the response.
        Nicely uncompressed, and readable.'''
        rawResponse = rawHeaders + '\r\n' + rawBody
        def rawResponser():
            for c in rawResponse:
                yield Yield
                yield c
        _sio = StringIO()
        _gzFileObj = GzipFile(filename=None, mode='wb', compresslevel=6, fileobj=_sio)
        _gzFileObj.write(rawBody); _gzFileObj.close()
        compressedBody = _sio.getvalue()

        compressedResponse = rawHeaders.replace('Content-Length: 12345\r\n', '') + 'Content-Encoding: gzip\r\n\r\n' + compressedBody
        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nAccept-Encoding: gzip;q=0.999, deflate;q=0.998, dontknowthisone;q=1\r\n\r\n', response=rawResponser(), compressResponse=True)
        self.assertEquals(compressedResponse, response)

    def testOnlyCompressBodyWhenCompressResponseIsOn(self):
        rawHeaders = 'HTTP/1.1 200 OK\r\nSome: Header\r\nContent-Length: 12345\r\nAnother: Header\r\n'
        rawBody = '''This is the response.
        Nicely uncompressed, and readable.'''
        rawResponse = rawHeaders + '\r\n' + rawBody
        def rawResponser():
            for c in rawResponse:
                yield c

        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nAccept-Encoding: deflate\r\n\r\n', response=rawResponser(), compressResponse=False)
        self.assertEquals(rawResponse, response)

        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nAccept-Encoding: deflate\r\n\r\n', response=rawResponser(), compressResponse=True)
        self.assertNotEqual(rawResponse, response)

    def testGetCompressedResponse_uncompressedWhenContentEncodingPresent(self):
        rawHeaders = 'HTTP/1.1 200 OK\r\nSome: Header\r\nContent-Length: 12345\r\nContent-Encoding: enlightened\r\n'
        rawBody = '''This is the response.
        *NOT* compressed.'''
        rawResponse = rawHeaders + '\r\n' + rawBody
        def rawResponser():
            for c in rawResponse:
                yield c
        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nAccept-Encoding: deflate\r\n\r\n', response=rawResponser(), compressResponse=True, extraStepAfterCompress=False)
        self.assertEquals(rawResponse, response)

    def testParseContentEncoding(self):
        self.assertEquals(['gzip'], parseContentEncoding('gzip'))
        self.assertEquals(['gzip'], parseContentEncoding('    gzip       '))
        self.assertEquals(['gzip', 'deflate'], parseContentEncoding('gzip, deflate'))
        self.assertEquals(['deflate', 'gzip'], parseContentEncoding('  deflate  ,    gzip '))

    def testParseAcceptEncoding(self):
        self.assertEquals(['gzip'], parseAcceptEncoding('gzip'))
        self.assertEquals(['gzip', 'deflate'], parseAcceptEncoding('gzip, deflate'))
        self.assertEquals(['gzip', 'deflate'], parseAcceptEncoding(' gzip  , deflate '))
        self.assertEquals(['deflate'], parseAcceptEncoding('gzip;q=0, deflate;q=1.0'))
        self.assertEquals(['deflate'], parseAcceptEncoding('gzip;q=0.00, deflate;q=1.001'))
        self.assertEquals(['deflate;media=range'], parseAcceptEncoding('gzip;q=0.00, deflate;media=range;q=1.001;I=amIgnored'))
        self.assertEquals(['text/xhtml+xml', 'x-gzip', 'text/html;level=2'], parseAcceptEncoding('text/html;level=2;q=0.005, text/xhtml+xml;q=0.7, x-gzip;q=0.6'))

    def testUpdateResponseHeaders(self):
        headers = 'HTTP/1.0 200 OK\r\nSome: Header\r\n\r\nThe Body'
        match = REGEXP.RESPONSE.match(headers)
        newHeaders, newBody = updateResponseHeaders(headers, match)

        self.assertEquals('HTTP/1.0 200 OK\r\nSome: Header\r\n\r\n', newHeaders)
        self.assertEquals('The Body', newBody)

        headers = 'HTTP/1.0 200 OK\r\nSome: Header\r\nContent-Length: 12345\r\nAnother: 1\r\n\r\nThe Body'
        match = REGEXP.RESPONSE.match(headers)
        newHeaders, newBody = updateResponseHeaders(headers, match, removeHeaders=['Content-Length'])

        self.assertEquals('HTTP/1.0 200 OK\r\nSome: Header\r\nAnother: 1\r\n\r\n', newHeaders)
        self.assertEquals('The Body', newBody)

        headers = 'HTTP/1.0 200 OK\r\nA: H\r\ncOnTeNt-LENGTh:\r\nB: I\r\n\r\nThe Body'
        match = REGEXP.RESPONSE.match(headers)
        newHeaders, newBody = updateResponseHeaders(headers, match, removeHeaders=['Content-Length'])

        self.assertEquals('HTTP/1.0 200 OK\r\nA: H\r\nB: I\r\n\r\n', newHeaders)
        self.assertEquals('The Body', newBody)

    def testUpdateResponseHeaders_addHeaders(self):
        headers = 'HTTP/1.0 200 OK\r\nA: H\r\n\r\nbody'
        match = REGEXP.RESPONSE.match(headers)
        newHeaders, newBody = updateResponseHeaders(headers, match, addHeaders={'Content-Encoding': 'deflate'})
        self.assertEquals(('HTTP/1.0 200 OK\r\nA: H\r\nContent-Encoding: deflate\r\n\r\n', 'body'), (newHeaders, newBody))

    def testUpdateResponseHeaders_removeHeaders(self):
        statusLineAndHeaders = 'HTTP/1.0 200 OK\r\nB: have\r\n\r\nbody'
        match = REGEXP.RESPONSE.match(statusLineAndHeaders)
        newSLandHeaders, newBody = updateResponseHeaders(statusLineAndHeaders, match, removeHeaders=['B'])
        self.assertEquals(('HTTP/1.0 200 OK\r\n\r\n', 'body'), (newSLandHeaders, newBody))

        statusLineAndHeaders = 'HTTP/1.0 200 OK\r\nB: have\r\n\r\nbody'
        match = REGEXP.RESPONSE.match(statusLineAndHeaders)
        newSLandHeaders, newBody = updateResponseHeaders(statusLineAndHeaders, match, removeHeaders=['Not-Found-Header'])
        self.assertEquals(('HTTP/1.0 200 OK\r\nB: have\r\n\r\n', 'body'), (newSLandHeaders, newBody))

        statusLineAndHeaders = 'HTTP/1.0 200 OK\r\nAnother: header\r\nB: have\r\nBe: haved\r\n\r\nbody'
        match = REGEXP.RESPONSE.match(statusLineAndHeaders)
        newSLandHeaders, newBody = updateResponseHeaders(statusLineAndHeaders, match, removeHeaders=['B'])
        self.assertEquals(('HTTP/1.0 200 OK\r\nAnother: header\r\nBe: haved\r\n\r\n', 'body'), (newSLandHeaders, newBody))

    def testUpdateResponseHeaders_requireAbsent(self):
        headers = 'HTTP/1.0 200 OK\r\nA: H\r\n\r\nbody'
        match = REGEXP.RESPONSE.match(headers)
        newHeaders, newBody = updateResponseHeaders(headers, match, requireAbsent=['Content-Encoding'])
        self.assertEquals(('HTTP/1.0 200 OK\r\nA: H\r\n\r\n', 'body'), (newHeaders, newBody))

        headers = 'HTTP/1.0 200 OK\r\nA: H\r\nContent-Encoding: Yes, Please\r\n\r\nbody'
        match = REGEXP.RESPONSE.match(headers)
        self.assertRaises(ValueError, lambda: updateResponseHeaders(headers, match, requireAbsent=['Content-Encoding']))

        headers = 'HTTP/1.0 200 OK\r\ncoNTent-ENCodIng:\r\n\r\nbody'
        match = REGEXP.RESPONSE.match(headers)
        self.assertRaises(ValueError, lambda: updateResponseHeaders(headers, match, requireAbsent=['Content-Encoding']))

        headers = 'HTTP/1.0 200 OK\r\nA: Content-Encoding\r\nOh: No\r\n\r\nbody'
        match = REGEXP.RESPONSE.match(headers)
        self.assertRaises(ValueError, lambda: updateResponseHeaders(headers, match, requireAbsent=['Content-Encoding', 'Oh']))

        headers = 'HTTP/1.0 200 OK\r\nA:\r\nB:\r\nC:\r\nD:\r\n\r\nbody'
        match = REGEXP.RESPONSE.match(headers)
        try:
            updateResponseHeaders(headers, match, requireAbsent=['B', 'C'])
        except ValueError, e:
            self.assertEquals('Response headers contained disallowed items: C, B', str(e))

    def testCloseConnection(self):
        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nConnection: close\r\nApe-Nut: Mies\r\n\r\n')
        self.assertEquals('The Response', response)
        self.assertEquals({}, self.reactor._readers)
        self.assertEquals({}, self.reactor._writers)

    def testSmallFragments(self):
        response = self.sendRequestAndReceiveResponse('GET /path/here HTTP/1.0\r\nConnection: close\r\nApe-Nut: Mies\r\n\r\n', recvSize=3)
        self.assertEquals('The Response', response)

    def testSmallFragmentsWhileSendingResponse(self):
        def response(**kwargs):
            yield 'some text that is longer than '
            yield 'the lenght of fragments sent'
        reactor = Reactor()
        server = HttpServer(reactor, self.port, response, recvSize=3)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
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

    def testHttpServerEncodesUnicode(self):
        unicodeString = u'some t\xe9xt' 
        oneStringLength = len(unicodeString.encode(getdefaultencoding()))
        self.assertTrue(len(unicodeString) != oneStringLength)
        def response(**kwargs):
            yield unicodeString * 6000
        reactor = Reactor()
        server = HttpServer(reactor, self.port, response, recvSize=3)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send('GET /path/here HTTP/1.0\r\nConnection: close\r\nApe-Nut: Mies\r\n\r\n')
        while not reactor._writers:
            reactor.step()
        reactor.step()
        fragment = sok.recv(100000) # will read about 49152 chars
        reactor.step()
        fragment += sok.recv(100000)
        self.assertEquals(oneStringLength * 6000, len(fragment))
        self.assertTrue("some t\xc3\xa9xt" in fragment, fragment)

    def testInvalidGETRequestStartsOnlyOneTimer(self):
        _httpserver.RECVSIZE = 3
        reactor = Reactor()
        timers = []
        orgAddTimer = reactor.addTimer
        def addTimerInterceptor(*timer):
            timers.append(timer)
            return orgAddTimer(*timer)
        reactor.addTimer = addTimerInterceptor
        server = HttpServer(reactor, self.port, None, timeout=0.01)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send('GET HTTP/1.0\r\n\r\n') # no path
        while select([sok],[], [], 0) != ([sok], [], []):
            reactor.step()
        response = sok.recv(4096)
        self.assertEquals('HTTP/1.0 400 Bad Request\r\n\r\n', response)
        self.assertEquals(1, len(timers))

    def testInvalidPOSTRequestStartsOnlyOneTimer(self):
        # problem in found in OAS, timers not removed properly when whole body hasnt been read yet
        _httpserver.RECVSIZE = 1
        reactor = Reactor()
        timers = []
        orgAddTimer = reactor.addTimer
        def addTimerInterceptor(*timer):
            timers.append(timer)
            return orgAddTimer(*timer)
        reactor.addTimer = addTimerInterceptor
        server = HttpServer(reactor, self.port, lambda **kwargs: (x for x in []), timeout=0.01)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send('POST / HTTP/1.0\r\nContent-Length: 10\r\n\r\n')
        reactor.step()
        sok.send(".")
        sleep(0.1)
        reactor.step()
        sok.send(".")
        reactor.step()
        sleep(0.1)
        while select([sok],[], [], 0) != ([sok], [], []):
            reactor.step()
        self.assertEquals(2, len(timers))



    def testInvalidRequestWithHalfHeader(self):
        reactor = Reactor()
        server = HttpServer(reactor, self.port, None, timeout=0.1)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send('POST / HTTP/1.0\r\n') 
        sok.send('Expect: something\r\n')
        sok.send('Content-Length: 5\r\n')
        sok.send('\r\n1234')
        sok.close()
        with self.stderr_replaced() as s:
            for i in range(4):
                reactor.step()
            self.assertEquals(1, len(reactor._readers))

    def testValidRequestResetsTimer(self):
        reactor = Reactor()
        server = HttpServer(reactor, self.port, lambda **kwargs: ('a' for a in range(3)), timeout=0.01, recvSize=3)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
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

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler, timeout=0.01)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
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

    def testPostMethodDeCompressesDeflatedBody_deflate(self):
        self.requestData = None
        def handler(**kwargs):
            self.requestData = kwargs

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler, timeout=0.01)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        bodyData = 'bodydatabodydata'
        bodyDataCompressed = compress(bodyData)
        contentLengthCompressed = len(bodyDataCompressed)
        sok.send(('POST / HTTP/1.0\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: %d\r\nContent-Encoding: deflate\r\n\r\n' % contentLengthCompressed) + bodyDataCompressed)

        while not self.requestData:
            reactor.step()
        self.assertEquals(dict, type(self.requestData))
        self.assertTrue('Headers' in self.requestData)
        headers = self.requestData['Headers']
        self.assertEquals('POST', self.requestData['Method'])
        self.assertEquals('application/x-www-form-urlencoded', headers['Content-Type'])
        self.assertEquals(contentLengthCompressed, int(headers['Content-Length']))  # TS: is this correct?, maybe decompressed length?

        self.assertTrue('Body' in self.requestData)
        self.assertEquals('bodydatabodydata', self.requestData['Body'])

    def testPostMethodDeCompressesDeflatedBody_gzip(self):
        self.requestData = None
        def handler(**kwargs):
            self.requestData = kwargs

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler, timeout=0.01)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        bodyData = 'bodydatabodydata'
        _sio = StringIO()
        _gzFileObj = GzipFile(filename=None, mode='wb', compresslevel=6, fileobj=_sio)
        _gzFileObj.write(bodyData); _gzFileObj.close()
        compressedBodyData = _sio.getvalue()
        bodyDataCompressed = compress(bodyData)
        contentLengthCompressed = len(bodyDataCompressed)
        sok.send(('POST / HTTP/1.0\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: %d\r\nContent-Encoding: gzip\r\n\r\n' % contentLengthCompressed) + bodyDataCompressed)

        while not self.requestData:
            reactor.step()
        self.assertEquals(dict, type(self.requestData))
        self.assertTrue('Headers' in self.requestData)
        headers = self.requestData['Headers']
        self.assertEquals('POST', self.requestData['Method'])
        self.assertEquals('application/x-www-form-urlencoded', headers['Content-Type'])
        self.assertEquals(contentLengthCompressed, int(headers['Content-Length']))

        self.assertTrue('Body' in self.requestData)
        self.assertEquals('bodydatabodydata', self.requestData['Body'])

    def testPostMethodDeCompressesDeflatedBody_x_deflate(self):
        self.requestData = None
        def handler(**kwargs):
            self.requestData = kwargs
            return
            yield

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler, timeout=0.01)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        bodyData = 'bodydatabodydata'
        bodyDataCompressed = compress(bodyData)
        contentLengthCompressed = len(bodyDataCompressed)
        sok.send(('POST / HTTP/1.0\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: %d\r\nContent-Encoding: x-deflate\r\n\r\n' % contentLengthCompressed) + bodyDataCompressed)

        while select([sok],[], [], 0) != ([sok], [], []):
            reactor.step()
        self.assertFalse(sok.recv(4096).startswith('HTTP/1.0 400 Bad Request'))

        # TS: minimalistic assert that it works too for x-deflate
        self.assertEquals('bodydatabodydata', self.requestData['Body'])

    def testPostMethodDeCompressesDeflatedBody_unrecognizedEncoding(self):
        self.requestData = None
        def handler(**kwargs):
            self.requestData = kwargs
            return
            yield

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler, timeout=0.01)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        bodyData = 'bodydatabodydata'
        bodyDataCompressed = compress(bodyData)
        contentLengthCompressed = len(bodyDataCompressed)
        sok.send(('POST / HTTP/1.0\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: %d\r\nContent-Encoding: unknown\r\n\r\n' % contentLengthCompressed) + bodyDataCompressed)

        while select([sok],[], [], 0) != ([sok], [], []):
            reactor.step()
        self.assertTrue(sok.recv(4096).startswith('HTTP/1.0 400 Bad Request'))

        self.assertEquals(None, self.requestData)

    def testPostMethodTimesOutOnBadBody(self):
        self.requestData = None
        def handler(**kwargs):
            self.requestData = kwargs

        done = []
        def onDone():
            fromServer = sok.recv(1024)
            self.assertTrue('HTTP/1.0 400 Bad Request' in fromServer)
            done.append(True)

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler, timeout=0.01)
        server.listen()
        reactor.addTimer(0.02, onDone)
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send('POST / HTTP/1.0\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: 8\r\n\r\n')

        while not done:
            reactor.step()

    def testReadChunkedPost(self):
        self.requestData = {}
        def handler(**kwargs):
            self.requestData = kwargs

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler, timeout=0.01, recvSize=3)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send('POST / HTTP/1.0\r\nContent-Type: application/x-www-form-urlencoded\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nabcde\r\n5\r\nfghij\r\n0\r\n')

        reactor.addTimer(0.2, lambda: self.fail("Test Stuck"))
        while self.requestData.get('Body', None) != 'abcdefghij':
            reactor.step()

    def testReadChunkedAndCompressedPost(self):
        postData = 'AhjBeehCeehAhjBeehCeehAhjBeehCeehAhjBeehCeeh'
        postDataCompressed = compress(postData)
        self.assertEquals(20, len(postDataCompressed))
        self.assertEquals(15, len(postDataCompressed[:15]))
        self.assertEquals(5, len(postDataCompressed[15:]))

        self.requestData = {}
        def handler(**kwargs):
            self.requestData = kwargs

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler, timeout=0.01, recvSize=3)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        postString = 'POST / HTTP/1.1\r\nContent-Type: application/x-www-form-urlencoded\r\nTransfer-Encoding: chunked\r\nContent-Encoding: deflate\r\n\r\nf\r\n%s\r\n5\r\n%s\r\n0\r\n' % (postDataCompressed[:15], postDataCompressed[15:])
        sok.send(postString)

        reactor.addTimer(0.2, lambda: self.fail("Test Stuck"))
        while self.requestData.get('Body', None) != postData:
            reactor.step()

    def testPostMultipartForm(self):
        httpRequest = open(inmydir('data/multipart-data-01')).read()
        self.requestData = {}
        def handler(**kwargs):
            self.requestData = kwargs

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send(httpRequest)

        reactor.addTimer(2, lambda: self.fail("Test Stuck"))
        while self.requestData.get('Form', None) == None:
            reactor.step()
        form = self.requestData['Form']
        self.assertEquals(4, len(form))
        self.assertEquals(['SOME ID'], form['id'])

    def XXX_testPostMultipartFormCompressed(self):
        """Not yet"""
        httpRequest = open(inmydir('data/multipart-data-01-compressed')).read()
        self.requestData = {}
        def handler(**kwargs):
            self.requestData = kwargs

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
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

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
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

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
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

    def testReadMultipartFormEndBoundary(self):
        httpRequest = open(inmydir('data/multipart-data-04')).read()
        self.requestData = {}
        def handler(**kwargs):
            self.requestData = kwargs

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send(httpRequest)

        reactor.addTimer(2, lambda: self.fail("Test Stuck"))
        while self.requestData.get('Form', None) == None:
            reactor.step()
        form = self.requestData['Form']
        self.assertEquals(1, len(form))
        self.assertEquals(3521*'X', form['id'][0])

    def testOnlyHandleAMaximumNrOfRequests(self):
        codes = []
        def handler(**kwargs):
            yield "OK"

        def error_handler(**kwargs):
            codes.append(kwargs['ResponseCode'])
            yield "FAIL"

        server = HttpServer(self.reactor, self.port, handler, errorHandler=error_handler, maxConnections=5)
        server.listen()

        self.reactor.getOpenConnections = lambda: 10

        sock = socket()
        sock.connect(('localhost', self.port))
        self.reactor.step()
        sock.send("GET / HTTP/1.0\r\n\r\n")
        self.reactor.step().step().step()
        server.shutdown()

        self.assertEquals('FAIL', sock.recv(1024))
        self.assertEquals([503], codes)

    def testOnlyHandleAMaximumNrOfRequestsBelowBoundary(self):
        def handler(**kwargs):
            yield "OK"

        def error_handler(**kwargs):
            yield "FAIL"

        server = HttpServer(self.reactor, self.port, handler, errorHandler=error_handler, maxConnections=10)
        server.listen()

        self.reactor.getOpenConnections = lambda: 5

        sock = socket()
        sock.connect(('localhost', self.port))
        self.reactor.step()
        sock.send("GET / HTTP/1.0\r\n\r\n")
        self.reactor.step().step().step()
        server.shutdown()

        self.assertEquals('OK', sock.recv(1024))

    def testDefaultErrorHandler(self):
        def handler(**kwargs):
            yield "OK"

        server = HttpServer(self.reactor, self.port, handler, maxConnections=5)
        server.listen()

        self.reactor.getOpenConnections = lambda: 10

        sock = socket()
        sock.connect(('localhost', self.port))
        self.reactor.step()
        sock.send("GET / HTTP/1.0\r\n\r\n")
        self.reactor.step().step().step()

        self.assertEquals('HTTP/1.0 503 Service Unavailable\r\n\r\n<html><head></head><body><h1>Service Unavailable</h1></body></html>', sock.recv(1024))
        server.shutdown()

    def testYieldInHttpServer(self):
        bucket = []
        def handler(RequestURI, **kwargs):
            yield 'A'
            while 'continue' not in bucket:
                yield Yield
            yield 'B'

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler)
        server.listen()
        sok = socket()
        sok.connect(('localhost', self.port))
        sok.send('GET /path/here HTTP/1.0\r\n\r\n')
        for i in xrange(500):
            reactor.step()
        self.assertEquals('A', sok.recv(100))
        bucket.append('continue')
        reactor.step()
        self.assertEquals('B', sok.recv(100))

    def testYieldPossibleUseCase(self):
        bucket = []
        result = []
        ready = []
        useYield = []
        workDone = []
        def handler(RequestURI, **kwargs):
            name = 'work' if 'aLotOfWork' in RequestURI else 'lazy'
            bucket.append('%s_START' % name)
            yield 'START'
            if '/aLotOfWork' in RequestURI:
                bucket.append('%s_part_1' % name)
                if True in useYield:
                    while not workDone:
                        yield Yield
                bucket.append('%s_part_2' % name)
            bucket.append('%s_END' % name)
            ready.append('yes')
            yield 'END'

        reactor = Reactor()
        server = HttpServer(reactor, self.port, handler)
        server.listen()

        def loopWithYield(use):
            del ready[:]
            del bucket[:]
            del result[:]
            del workDone[:]
            useYield[:] = [use]
            sok0 = socket()
            sok0.connect(('localhost', self.port))
            sok0.send('GET /aLotOfWork HTTP/1.0\r\n\r\n')
            sok1 = socket()
            sok1.connect(('localhost', self.port))
            sok1.send('GET /path/here HTTP/1.0\r\n\r\n')
            sleep(0.02)
            while ready != ['yes']:
                reactor.step()
                if bucket:
                    result.append(set(bucket))
                    del bucket[:]
            workDone.append(True)
            while ready != ['yes', 'yes']:
                reactor.step()
                if bucket:
                    result.append(set(bucket))
                    del bucket[:]
            return result

        self.assertEquals([
                set(['work_START']),
                set(['lazy_START', 'work_part_1', 'work_part_2', 'work_END']),
                set(['lazy_END'])
           ], loopWithYield(False))
        self.assertEquals([
                set(['work_START']),
                set(['lazy_START', 'work_part_1']),
                set(['lazy_END']),
                set(['work_part_2', 'work_END']),
           ], loopWithYield(True))

