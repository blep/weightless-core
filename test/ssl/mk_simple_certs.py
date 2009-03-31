#!/usr/bin/env python2.5

from OpenSSL import crypto
from certgen import createKeyPair, createCertRequest, createCertificate, TYPE_RSA

from sys import stdin

cakey = createKeyPair(TYPE_RSA, 1024)
careq = createCertRequest(cakey, CN='Certificate Authority')
cacert = createCertificate(careq, (careq, cakey), 0, (0, 60*60*24*365*5)) # five years
open('CA.pkey', 'w').write(crypto.dump_privatekey(crypto.FILETYPE_PEM, cakey))
open('CA.cert', 'w').write(crypto.dump_certificate(crypto.FILETYPE_PEM, cacert))


CN = raw_input("CN: ").strip()
pkey = createKeyPair(TYPE_RSA, 1024)
req = createCertRequest(pkey, CN=CN)
cert = createCertificate(req, (cacert, cakey), 1, (0, 60*60*24*365*5)) # five years
open('server.pkey', 'w').write(crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
open('server.cert', 'w').write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
