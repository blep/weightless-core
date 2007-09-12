## begin license ##
#
#    Weightless is a High Performance Asynchronous Networking Library
#    Copyright (C) 2006-2007 Seek You Too B.V. (CQ2) http://www.cq2.nl
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
from time import sleep
from weightless import WlService, WlDict
from weightless.wlsocket import WlSelect
from weightless.wlhttp import recvRequest
from weightless.http import HTTP
from weightless import compose
from weightless.wlhttp import recvRequest, sendBody
from functools import partial as curry
from urlparse import urlsplit
from types import GeneratorType
from cq2utils import profileit

#import psyco
#psyco.full()

#from cq2utils import cq2thread
#cq2thread.profilingEnabled = True

select = WlSelect(dontCallUsWeCallYou=True)
service = WlService(select)

class AComponent:
	def display(self, x, y):
		return (x for x in ['a'*x*y])

def parseArgs(uri):
	if uri.query:
		args = (arg.split('=') for arg in uri.query.split('&'))
		return dict((name, eval(value, {'__builtins__': {}})) for name, value in args)
	return {}

def handler():
	while True:
		req = yield recvRequest()
		uri = urlsplit(req.RequestURI)
		try:
			selectors = uri.path[1:].split('/', 2)
			namespace, componentname = selectors[:2]
			methodName = selectors[2] if len(selectors) > 2 else 'display'
			component = AComponent()
		except:
			component = None
		if component is None:
			yield HTTP.Response.StatusLine % {
				'version': 1.1,
				'status': 404,
				'reason': 'Not Found'}
		else:
			args = parseArgs(uri)
			method = getattr(component, methodName)
			data = method(**args)
			mimetype = 'text/plain' if type(data) != GeneratorType else 'image/png'
			yield HTTP.Response.StatusLine % {
				'version': 1.1,
				'status': 200,
				'reason': 'OK'}
			headers = {'Content-Type': mimetype, 'Transfer-Encoding': 'chunked'}
			response = WlDict()
			response.headers = WlDict(headers)
			yield HTTP.Message.Headers(headers)
			yield sendBody(response, data)
			#if hasattr(req.headers, 'Connection') and  req.headers.Connection == 'close':
			return

def sinkFactory():
	return handler()

service.listen('127.0.0.1', 1234, sinkFactory)

#profileit.profile(select._loop)
select._loop()

try:
	while True:
		print '.'
		sleep(1)
except KeyboardInterrupt:
	pass

service.stop()
