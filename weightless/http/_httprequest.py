## begin license ##
#
#    Weightless is a High Performance Asynchronous Networking Library
#    See http://weightless.io
#    Copyright (C) 2010-2011 Seek You Too (CQ2) http://www.cq2.nl
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

from sys import exc_info, getdefaultencoding
from weightless.http import Suspend
from weightless.core import identify
from socket import socket, error as SocketError, SOL_SOCKET, SO_ERROR, SHUT_WR, SHUT_RD
from errno import EINPROGRESS

@identify
def _do(method, host, port, request, body=None, headers=None):
    this = yield # this generator, from @identify
    suspend = yield # suspend object, from Suspend.__call__
    sok = socket()
    sok.setblocking(0)
    #sok.settimeout(1.0)
    try:
        sok.connect((host, port))
    except SocketError, (errno, msg):
        if errno != EINPROGRESS:
            raise
    suspend._reactor.addWriter(sok, this.next)
    yield
    try:
        err = sok.getsockopt(SOL_SOCKET, SO_ERROR)
        if err != 0:    # connection created succesfully?
            raise IOError(err)
        yield
        suspend._reactor.removeWriter(sok)
        # error checking
        _sendHttpHeaders(sok, method, request, headers)
        if body:
            data = body
            if type(data) is unicode:
                data = data.encode(getdefaultencoding())
            sentBytes = 0
            suspend._reactor.addWriter(sok, this.next)
            while data != "":
                size = sok.send(data)
                data = data[size:]
                yield
            suspend._reactor.removeWriter(sok)
        sok.shutdown(SHUT_WR)
        #sok.shutdown(WRITER)
        suspend._reactor.addReader(sok, this.next)
        responses = []
        while True:
            yield
            response = sok.recv(4096) # error checking
            if response == '':
                break
            responses.append(response)
        suspend._reactor.removeReader(sok)
        #sok.shutdown(READER)
        sok.close()
        suspend.resume(''.join(responses))
    except Exception, e:
        suspend.throw(*exc_info())
    yield

def _httpRequest(method, request, headers):
    httpVersion = '1.1' if headers and 'Host' in headers else '1.0'
    return "%s %s HTTP/%s\r\n" % (method, request, httpVersion)
    
def _sendHttpHeaders(sok, method, request, headers):
    sok.send(_httpRequest(method, request, headers))
    if headers:
        sok.send(''.join('%s: %s\r\n' % i for i in headers.items()))
    sok.send('\r\n')

def httpget(host, port, request, headers=None):
    s = Suspend(_do('GET', host, port, request, headers=headers).send)
    yield s
    result = s.getResult()
    raise StopIteration(result)

def httppost(host, port, request, body, headers=None):
    s = Suspend(_do('POST', host, port, request, body, headers=headers).send)
    yield s
    result = s.getResult()
    raise StopIteration(result)
