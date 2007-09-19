from unittest import TestCase
from weightless import Reactor, gio

class GioTest(TestCase):

    def testOpen(self):
        reactor = Reactor()
        def eventGenerator():
            self.sok = yield gio.open('data/testdata5kb')
        gio.Gio(reactor, eventGenerator())
        self.assertEquals('data/testdata5kb', self.sok._sok.name)

    def testSokRead(self):
        reactor = Reactor()
        def eventGenerator():
            sok = yield gio.open('data/testdata5kb')
            self.data = yield sok.read()
        gio.Gio(reactor, eventGenerator())
        reactor.step()
        self.assertEquals('\xe4\xd5VHv\xa3V\x87Vi', self.data[:10])

    def testWriteRead(self):
        reactor = Reactor()
        def eventGenerator():
            sok = yield gio.open('data/tmp01', 'w')
            yield sok.write('ape')
            yield sok.close()
            sok = yield gio.open('data/tmp01')
            self.data = yield sok.read()
        gio.Gio(reactor, eventGenerator())
        reactor.step()
        reactor.step()
        self.assertEquals('ape', self.data)

    def testNonExistingFile(self):
        def eventGenerator():
            try:
                sok = yield gio.open('nonexisting')
            except IOError, e:
                self.assertEquals("[Errno 2] No such file or directory: 'nonexisting'", str(e))
        try:
            gio.Gio('reactor', eventGenerator())
        except IOError, e:
            self.fail(e)