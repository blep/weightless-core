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
from _acceptor import Acceptor
from weightless.http import REGEXP, FORMAT, HTTP, parseHeaders, parseHeader
from socket import SHUT_RDWR, error as SocketError, MSG_DONTWAIT
from tempfile import TemporaryFile
from email import message_from_file as parse_mime_message

from OpenSSL import SSL
from socket import socket, ssl,  SOL_SOCKET, SO_REUSEADDR, SO_LINGER
from struct import pack


RECVSIZE = 4096
CRLF_LEN = 2

def HttpServer(reactor, port, generatorFactory, timeout=1, recvSize=RECVSIZE, prio=None):
    """Factory that creates a HTTP server listening on port, calling generatorFactory for each new connection.  When a client does not send a valid HTTP request, it is disconnected after timeout seconds. The generatorFactory is called with the HTTP Status and Headers as arguments.  It is expected to return a generator that produces the response -- including the Status line and Headers -- to be send to the client."""
    return Acceptor(reactor, port, lambda sok: HttpHandler(reactor, sok, generatorFactory, timeout, recvSize, prio=prio), prio=prio)

def HttpsServer(reactor, port, generatorFactory, timeout=1, recvSize=RECVSIZE, prio=None, certfile='', keyfile=''):
    """Factory that creates a HTTP server listening on port, calling generatorFactory for each new connection.  When a client does not send a valid HTTP request, it is disconnected after timeout seconds. The generatorFactory is called with the HTTP Status and Headers as arguments.  It is expected to return a generator that produces the response -- including the Status line and Headers -- to be send to the client."""
    def verify_cb(conn, cert, errnum, depth, ok):
        # This obviously has to be updated
        print 'Got certificate: %s' % cert.get_subject()
        return ok

    # Initialize context
    ctx = SSL.Context(SSL.SSLv23_METHOD)
    ctx.set_session_id('weightless')
    ctx.set_options(SSL.OP_NO_SSLv2)
    ctx.set_verify(SSL.VERIFY_PEER, verify_cb) # Demand a certificate
    ctx.use_privatekey_file (keyfile)
    ctx.use_certificate_file(certfile)

    # Set up server
    secureSok = SSL.Connection(ctx, socket())
    secureSok.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    secureSok.setsockopt(SOL_SOCKET, SO_LINGER, pack('ii', 0, 0))
    secureSok.bind(('0.0.0.0', port))
    secureSok.listen(127)

    return Acceptor(reactor, port, lambda s: HttpsHandler(reactor, s, generatorFactory, timeout, recvSize, prio=prio), prio=prio, sok=secureSok)

from sys import stdout

class HttpHandler(object):
    def __init__(self, reactor, sok, generatorFactory, timeout, recvSize=RECVSIZE, prio=None):
        self._reactor = reactor
        self._sok = sok
        self._generatorFactory = generatorFactory
        self._dataBuffer = ''
        self._rest = None
        self._timeout = timeout
        self._timer = None
        self._recvSize = recvSize
        self.request = None
        self._dealWithCall = self._readHeaders
        self._prio = prio

    def __call__(self):
        part = self._sok.recv(self._recvSize)
        self._dataBuffer += part
        self._dealWithCall()

    def setCallDealer(self, aMethod):
        self._dealWithCall = aMethod
        self._dealWithCall()

    def _readHeaders(self):
        match = REGEXP.REQUEST.match(self._dataBuffer)
        if not match:
            if not self._timer:
                self._timer = self._reactor.addTimer(self._timeout, self._badRequest)
            return # for more data
        if self._timer:
            self._reactor.removeTimer(self._timer)
            self._timer = None
        self.request = match.groupdict()
        self.request['Body'] = ''
        self.request['Headers'] = parseHeaders(self.request['_headers'])
        matchEnd = match.end()
        self._dataBuffer = self._dataBuffer[matchEnd:]
        if 'Content-Type' in self.request['Headers']:
            cType, pDict = parseHeader(self.request['Headers']['Content-Type'])
            if cType[:10] == 'multipart/':
                self._tempfile = TemporaryFile('w+b')
                #self._tempfile = open('/tmp/mimetest', 'w+b')
                self._tempfile.write('Content-Type: %s\r\n\r\n' % self.request['Headers']['Content-Type'])
                self.setCallDealer(lambda: self._readMultiForm(pDict['boundary']))
                return
        if 'Expect' in self.request['Headers']:
            self._sok.send('HTTP/1.1 100 Continue\r\n\r\n')
        self.setCallDealer(self._readBody)

    def _readMultiForm(self, boundary):
        self._tempfile.write(self._dataBuffer)
        if self._timer:
            self._reactor.removeTimer(self._timer)
            self._timer = None
        if self._dataBuffer.endswith("\r\n--%s--\r\n" % boundary):
            self._tempfile.seek(0)

            form = {}
            for msg in parse_mime_message(self._tempfile).get_payload():
                cType, pDict = parseHeader(msg['Content-Disposition'])
                contentType = msg.get_content_type()
                fieldName = pDict['name'][1:-1]
                if not fieldName in form:
                    form[fieldName] = []

                if contentType == 'text/plain':
                    form[fieldName].append(msg.get_payload())
                else:
                    filename = self._processFilename(pDict.get('filename', '')[1:-1])
                    form[fieldName].append((filename, contentType, msg.get_payload()))

            self.request['Form'] = form
            self._tempfile.close()
            self.finalize()
            return


        self._dataBuffer= ''
        if not self._timer:
            self._timer = self._reactor.addTimer(self._timeout, self._badRequest)

    def _processFilename(self, filename):
        parts = filename.split('\\')
        if len(parts) == 1:
            return filename
        return parts[-1]

    def _readBody(self):
        if self.request['Method'] == 'GET':
            self.finalize()
        elif self.request['Method'] == 'POST':
            if 'Content-Length' in self.request['Headers']:
                contentLength = int(self.request['Headers']['Content-Length'])

                if len(self._dataBuffer) < contentLength:
                    if not self._timer:
                        self._timer = self._reactor.addTimer(self._timeout, self._badRequest)
                    return
                if self._timer:
                    self._reactor.removeTimer(self._timer)
                    self._timer = None

                self.request['Body'] = self._dataBuffer
                self.finalize()
            elif 'Transfer-Encoding' in self.request['Headers'] and self.request['Headers']['Transfer-Encoding'] == 'chunked':
                self.setCallDealer(self._readChunk)
            else:
                self.finalize()
        else:
            self.finalize()

    def _readChunk(self):
        match = REGEXP.CHUNK_SIZE_LINE.match(self._dataBuffer)
        if not match:
            if not self._timer:
                self._timer = self._reactor.addTimer(self._timeout, self._badRequest)
            return # for more data
        if self._timer:
            self._reactor.removeTimer(self._timer)
            self._timer = None
        self._chunkSize = int(match.groupdict()['ChunkSize'], 16)
        self._dataBuffer = self._dataBuffer[match.end():]
        self.setCallDealer(self._readChunkBody)

    def _readChunkBody(self):
        if self._chunkSize == 0:
            self.finalize()
        else:
            if len(self._dataBuffer) < self._chunkSize + CRLF_LEN:
                if not self._timer:
                    self._timer = self._reactor.addTimer(self._timeout, self._badRequest)
                return # for more data
            if self._timer:
                self._reactor.removeTimer(self._timer)
                self._timer = None
            self.request['Body'] += self._dataBuffer[:self._chunkSize]
            self._dataBuffer = self._dataBuffer[self._chunkSize + CRLF_LEN:]
            self.setCallDealer(self._readChunk)

    def finalize(self):
        del self.request['_headers']
        self.request['Client'] = self._sok.getpeername()
        self._handler = self._generatorFactory(**self.request)
        self._reactor.removeReader(self._sok)
        self._reactor.addWriter(self._sok, self._writeResponse, prio=self._prio)

    def _badRequest(self):
        self._sok.send('HTTP/1.0 400 Bad Request\r\n\r\n')
        self._reactor.removeReader(self._sok)
        self._sok.shutdown(SHUT_RDWR)
        self._sok.close()

    def _writeResponse(self):
        try:
            if self._rest:
                data = self._rest
            else:
                data = self._handler.next()
            sent = self._sok.send(data, MSG_DONTWAIT)
            if sent < len(data):
                self._rest = data[sent:]
            else:
                self._rest = None
        except StopIteration:
            self._closeConnection()
        except:
            self._closeConnection()
            raise

    def _closeConnection(self):
        self._reactor.removeWriter(self._sok)

        try:
            self._sok.shutdown(SHUT_RDWR)
        except SocketError, e:
            code, message = e.args
            if code == 107:
                pass # KVS: not well understood, not tested. It seems some quick (local) servers close the connection before this point is reached. It may happen more generally. In any case, it is based on a truely existing phenomomon
            else:
                raise
        self._sok.close()

class HttpsHandler(HttpHandler):
    def __call__(self):
        try:
            part = self._sok.recv(self._recvSize)
        except (SSL.WantReadError, SSL.WantWriteError, SSL.WantX509LookupError):
            print "exception in read"
            pass
        except Exception, e:
            print "EXCEPTION", str(e)
            self._closeDuringRead()
        else:
            self._dataBuffer += part
            self._dealWithCall()

    def _closeDuringRead(self):
        self._reactor.removeReader(self._sok)
        self._sok.shutdown()
        self._sok.close()

    def _closeConnection(self):
        self._reactor.removeWriter(self._sok)
        self._sok.shutdown()
        self._sok.close()
