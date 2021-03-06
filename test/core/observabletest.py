# -*- coding: utf-8 -*-
## begin license ##
#
# "Weightless" is a High Performance Asynchronous Networking Library. See http://weightless.io
#
# Copyright (C) 2007-2009 SURF Foundation. http://www.surf.nl
# Copyright (C) 2007 SURFnet. http://www.surfnet.nl
# Copyright (C) 2007-2011 Seek You Too (CQ2) http://www.cq2.nl
# Copyright (C) 2007-2009 Stichting Kennisnet Ict op school. http://www.kennisnetictopschool.nl
# Copyright (C) 2010 Stichting Kennisnet http://www.kennisnet.nl
# Copyright (C) 2011-2013 Seecr (Seek You Too B.V.) http://seecr.nl
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

import gc
from sys import exc_info
from traceback import format_tb
from inspect import isframe, getframeinfo
from types import GeneratorType
from functools import partial
from weightless.core import compose, Yield, Observable, Transparent, be, tostring, NoneOfTheObserversRespond, DeclineMessage, cextension
from weightless.core._observable import AllMessage, AnyMessage, DoMessage, OnceMessage
from unittest import TestCase
from seecr.test import CallTrace

fileDict = {
    '__file__' : __file__.replace(".pyc", ".py")
}


def skip_if(condition):
    class Noop(object): pass
    def do_not_skip(test): return test
    def do_skip(test): return Noop()
    return do_skip if condition else do_not_skip

class ObservableTest(TestCase):
    def testAllWithoutImplementers(self):
        observable = Observable()
        responses = observable.all.someMethodNobodyIsListeningTo()
        self.assertEquals([], list(compose(responses)))

    def testAllWithOneImplementer(self):
        class A(object):
            def f(self):
                yield A.f
        root = be((Observable(), (A(),),))
        self.assertEquals([A.f], list(compose(root.all.f())))

    def testAllWithOneImplementerButMoreListening(self):
        class A(object):
            pass
        class B(object):
            def f(self):
                yield B.f
        root = be((Observable(), (A(),), (B(),)))
        self.assertEquals([B.f], list(compose(root.all.f())))

    def testAllWithMoreImplementers(self):
        class A(object):
            def f(self):
                yield A.f
        class B(object):
            def f(self):
                yield B.f
        root = be((Observable(), (A(),), (B(),)))
        self.assertEquals([A.f, B.f], list(compose(root.all.f())))

    def testAllWithException(self):
        class A(object):
            def f(self):
                raise Exception(A.f)
                yield
        class B(object):
            def f(self):
                yield Yield
        root = be((Observable(), (A(),), (B(),)))
        c = compose(root.all.f())
        try:
            c.next()
            self.fail()
        except Exception, e:
            self.assertEquals(A.f, e.args[0])
        root = be((Observable(), (B(),), (A(),))) # other way around
        c = compose(root.all.f())
        c.next()
        try:
            c.next()
            self.fail()
        except Exception, e:
            self.assertEquals(A.f, e.args[0])

    def testAllUnknown(self):
        class A(object):
            def all_unknown(self, *args, **kwargs):
                yield args, kwargs
        root = be((Observable(), (A(),)))
        r = compose(root.all.unknownmessage(1, two=2)).next()
        self.assertEquals((('unknownmessage', 1), {'two': 2}), r)

    def testAllAssertsNoneReturnValues(self):
        class A(object):
            def f(self):
                raise StopIteration(1)
                yield
            def all_unknown(self, message, *args, **kwargs):
                raise StopIteration(2)
                yield
        root = be((Observable(), (A(),)))
        g = compose(root.all.f())
        try:
            g.next()
            self.fail("Should not happen")
        except AssertionError, e:
            self.assertTrue("<bound method A.f of <core.observabletest.A object at 0x" in str(e), str(e))
            self.assertTrue(">> returned '1'" in str(e), str(e))
        g = compose(root.all.x())
        try:
            g.next()
            self.fail("Should not happen")
        except AssertionError, e:
            self.assertTrue("> returned '2'" in str(e), str(e))
            if not cextension:
                self.assertTrue("<bound method A.all_unknown of <core.observabletest.A object at 0x" in str(e), str(e))

    @skip_if(cextension)
    def testAllAssertsResultOfCallIsGeneratorOrComposed(self):
        class A(object):
            def f(self):
                return 42
            def all_unknown(self, message, *args, **kwargs):
                return 42
        root = be((Observable(), (Transparent(), (A(),))))
        g = compose(root.all.f())
        try:
            g.next()
            self.fail("Should not happen")
        except AssertionError, e:
            self.assertTrue("<bound method A.f of <core.observabletest.A object at 0x" in str(e), str(e))
            self.assertTrue(">> should have resulted in a generator." in str(e), str(e))
            self.assertFunctionsOnTraceback("testAllAssertsResultOfCallIsGeneratorOrComposed", "all_unknown", "verifyMethodResult")

        g = compose(root.all.undefinedMethod())
        try:
            g.next()
            self.fail("Should not happen")
        except AssertionError, e:
            self.assertTrue("<bound method A.all_unknown of <core.observabletest.A object at 0x" in str(e), str(e))
            self.assertTrue(">> should have resulted in a generator." in str(e), str(e))

    def testOnceAssertsNoneReturnValues(self):
        # OnceMessage assertion on None: #1a "normal object"
        class AnObject(object):
            def f(self):
                raise StopIteration(1)
                yield

        # OnceMessage assertion on None: #1b "Observable"
        class AnObservable(Observable):
            def g(self):
                raise StopIteration(1)
                yield

        root = be(
        (Observable(), 
            (AnObject(),),
            (AnObservable(),),
        ))
        composed = compose(root.once.f())
        try:
            composed.next()
            self.fail("Should not happen")
        except AssertionError, e:
            self.assertTrue("<bound method AnObject.f of <core.observabletest.AnObject object at 0x" in str(e), str(e))
            self.assertTrue(">> returned '1'" in str(e), str(e))

        root = be((Observable(), (AnObservable(),)))
        composed = compose(root.once.g())
        try:
            composed.next()
            self.fail("Should not happen")
        except AssertionError, e:
            self.assertTrue("<bound method AnObservable.g of AnObservable(name=None)" in str(e), str(e))
            self.assertTrue("> returned '1'" in str(e), str(e))

    def testOnceAssertsRecursivenessGivesNoReturnValue(self):
        # This will normally never happen.
        class AnObservable(Observable):
            def g(self):
                raise StopIteration(1)
                yield
        class MockedOnceMessageSelf(OnceMessage):
            pass
        def retvalGen(*args, **kwargs):
            raise StopIteration(1)
            yield
        oncedObservable = AnObservable()
        mockedSelf = MockedOnceMessageSelf(observers=oncedObservable._observers, message='noRelevantMethodHere', observable='AnObservableObject(name=None)')
        mockedSelf._callonce = retvalGen

        composed = compose(OnceMessage._callonce(mockedSelf, observers=[AnObservable()], args=(), kwargs={}, done=set()))
        try:
            composed.next()
            self.fail("Should not happen")
        except AssertionError, e:
            self.assertEquals("OnceMessage of AnObservableObject(name=None) returned '1', but must always be None", str(e))

    def testAnyOrCallCallsFirstImplementer(self):
        class A(object):
            def f(self):
                raise StopIteration(A.f)
                yield
            def f_sync(self):
                return A.f
        class B(object):
            def f(self):
                raise StopIteration(B.f)
                yield
            def f_sync(self):
                return B.f
            def g(self):
                raise StopIteration(B.g)
                yield
            def g_sync(self):
                return B.g
        root = be((Observable(), (A(),), (B(),)))

        try:
            compose(root.any.f()).next()
            self.fail('Should not happen')
        except StopIteration, e:
            self.assertEquals((A.f,), e.args)
        try:
            compose(root.any.g()).next()
            self.fail('Should not happen')
        except StopIteration, e:
            self.assertEquals((B.g,), e.args)

        self.assertEquals(A.f, root.call.f_sync())
        self.assertEquals(B.g, root.call.g_sync())

    def testAnyViaOther(self):
        class A(Observable):
            def f(self):
                response = yield self.any.f()
                raise StopIteration(response)
        class B(object):
            def f(self):
                yield "data"
                raise StopIteration('retval')
        root = be((Observable(), ((A(), (B(),)))))
        self.assertEquals(GeneratorType, type(root.any.f()))
        self.assertEquals(["data"], list(compose(root.any.f())))

        composed = compose(root.any.f())
        try:
            composed.next()  # 'data'
            composed.next()  # return 'retval'
            self.fail('Should not happen')
        except StopIteration, e:
            self.assertEquals(('retval',), e.args)

    @skip_if(cextension)
    def testAnyAssertsResultOfCallIsGeneratorOrComposed(self):
        class A(object):
            def f(self):
                return 42
            def any_unknown(self, message, *args, **kwargs):
                return 42
        root = be((Observable(), (A(),)))
        try:
            compose(root.any.f()).next()
            self.fail('Should not happen')
        except AssertionError, e:
            self.assertTrue("<bound method A.f of <core.observabletest.A object at 0x" in str(e), str(e))
            self.assertTrue(">> should have resulted in a generator." in str(e), str(e))

        try:
            compose(root.any.undefinedMethod()).next()
            self.fail('Should not happen')
        except AssertionError, e:
            self.assertTrue("<bound method A.any_unknown of <core.observabletest.A object at 0x" in str(e), str(e))
            self.assertTrue(">> should have resulted in a generator." in str(e), str(e))

    def testAnyViaUnknown(self):
        class A(object):
            def any_unknown(self, message, *args, **kwargs):
                raise StopIteration((message, args, kwargs), )
                yield
        root = be((Observable(), (A(),)))
        try: compose(root.any.f(1, a=2)).next()
        except StopIteration, e: r = e.args[0]
        self.assertEquals(('f', (1,), {'a': 2}), r)

    def testCallViaUnknown(self):
        class A(object):
            def call_unknown(self, message, *args, **kwargs):
                return message, args, kwargs
        root = be((Observable(), (A(),)))
        r = root.call.f(1, a=2)
        self.assertEquals(('f', (1,), {'a': 2}), r)

    def testDoReturnsNone(self):
        observable = Observable()
        r = observable.do.f()
        self.assertEquals(None, r)

    def testDoCallsAllObservers(self):
        called = []
        class A(object):
            def f(self):
                called.append(A.f)
        class B(object):
            def f(self):
                called.append(B.f)
        root = be((Observable(), (A(),), (B(),)))
        root.do.f()
        self.assertEquals([A.f, B.f], called)

    def testDoViaUnknown(self):
        called = []
        class A(object):
            def do_unknown(self, message, *args, **kwargs):
                called.append((message, args, kwargs))
        root = be((Observable(), (A(),)))
        root.do.f()
        self.assertEquals([('f', (), {})], called)

    @skip_if(cextension)
    def testDoAssertsIndividualCallsReturnNone(self):
        class A(object):
            def f(self):
                return
                yield
            def do_unknown(self, message, *args, **kwargs):
                return 42
        root = be((Observable(), (A(),)))

        try:
            root.do.f()
            self.fail('Should not happen')
        except AssertionError, e:
            self.assertTrue("<bound method A.f of <core.observabletest.A object at 0x" in str(e), str(e))
            self.assertTrue(">> returned '<generator object" in str(e), str(e))

        try:
            root.do.undefinedMethod()
            self.fail('Should not happen')
        except AssertionError, e:
            self.assertTrue("<bound method A.do_unknown of <core.observabletest.A object at 0x" in str(e), str(e))
            self.assertTrue(">> returned '42'" in str(e), str(e))

    def testUnknownDispatchingNoImplementation(self):
        observable = Observable()
        class A(object):
            pass
        observable.addObserver(A())
        retval = observable.all.unknown('non_existing_method', 'one')
        self.assertEquals([], list(compose(retval)))

    def testUnknownDispatching(self):
        observable = Observable()
        class Listener(object):
            def method(inner, one):
                return one + " another"
        observable.addObserver(Listener())
        retval = observable.call.unknown('method', 'one')
        self.assertEquals('one another', retval)

    def testUnknownDispatchingBackToUnknown(self):
        observable = Observable()
        class A(object):
            def call_unknown(self, message, one):
                return "via unknown " + one
        observable.addObserver(A())
        retval = observable.call.unknown('non_existing_method', 'one')
        self.assertEquals("via unknown one", retval)

    def testUnknownIsEquivalentToNormalCall(self):
        observable = Observable()
        class A(object):
            def normal(self):
                return 'normal'
            def call_unknown(self, message, *args, **kwargs):
                return 'normal'
        observable.addObserver(A())
        result1 = observable.call.unknown('normal')
        result2 = observable.call.unknown('other')
        self.assertEquals(result1, result2)

    def testBeOne(self):
        observer = Observable()
        root = be((observer,))
        self.assertEquals(root, observer)

    def testBeTwo(self):
        observable = Observable()
        child0 = Observable()
        child1 = Observable()
        root = be((observable, (child0,), (child1,)))
        self.assertEquals([child0, child1], observable._observers)

    def testBeTree(self):
        observable = Observable()
        child0 = Observable()
        child1 = Observable()
        root = be((observable, (child0, (child1,))))
        self.assertEquals([child0], root._observers)
        self.assertEquals([child1], child0._observers)

    def testAddStrandEmptyList(self):
        observable = Observable()
        observable.addStrand((), [])
        self.assertEquals([], observable._observers)

    def testProperErrorMessage(self):
        observable = Observable()
        try:
            answer = list(compose(observable.any.gimmeAnswer('please')))
            self.fail('should raise NoneOfTheObserversRespond')
        except NoneOfTheObserversRespond, e:
            self.assertFunctionsOnTraceback("testProperErrorMessage", "any")
            self.assertEquals('None of the 0 observers respond to gimmeAnswer(...)', str(e))

    def testProperErrorMessageWhenArgsDoNotMatch(self):
        observable = Observable()
        class YesObserver:
            def yes(self, oneArg): pass
        observable.addObserver(YesObserver())
        try:
            answer = observable.call.yes()
            self.fail('should raise TypeError')
        except TypeError, e:
            self.assertEquals('yes() takes exactly 2 arguments (1 given)', str(e))

    def testWhatItIs(self):
        def anAction():
            pass
        events = []
        class A(Observable):
            def dataflow(this): #all
                yield this.all.dataflow()
            def interface(this): #call
                return this.call.interface()
            def async_interface(this): # any
                r = yield this.any.async_interface()
                raise StopIteration(r)
            def event(this): #do
                this.do.event()
        class B(Observable):
            def dataflow(this): #all
                yield this.all.dataflow()
            def interface(this): #call
                return this.call.interface()
            def async_interface(this): #any
                r = yield this.any.async_interface()
                raise StopIteration(r)
            def event(this): #do
                this.do.event()
        class C(Observable):
            def dataflow(this): #all
                x = yield
                yield x * 'C'
            def interface(this): #call
                return 'C'
            def async_interface(this): #any
                yield anAction
                x = yield
                yield x * 'C'
                raise StopIteration(x)
            def event(this): #do
                events.append('C')
        class D(Observable):
            def dataflow(this): #all
                x = yield
                yield x * 'D'
            def interface(this): #call
                raise Exception('hell')
            def async_interface(this): #any
                raise Exception('hell')
            def event(this): #do
                events.append('D')
        t = be((Observable(),
                    (A(),
                        (B(),
                            (C(),),
                            (D(),),
                        )
                    )
                ))
        result = compose(t.all.dataflow())
        result.next()
        r = result.send(2)
        self.assertEquals('CC', r)
        result.next()
        r = result.send(3)
        self.assertEquals('DDD', r)

        result = t.call.interface()
        self.assertEquals('C', result)

        noResult = t.do.event()
        self.assertEquals(None, noResult)
        self.assertEquals(['C', 'D'], events)

        result = compose(t.any.async_interface())
        an_action = result.next()
        self.assertEquals(anAction, an_action)
        result.next()
        r = result.send(5)
        self.assertEquals('CCCCC', r)
        try:
            result.next()
            self.fail()
        except StopIteration, e:
            self.assertEquals((5,), e.args)

    def testTransparentUnknownImplementationIsVisibleOnTraceback(self):
        class Leaf(Observable):
            def aCall(self):
                raise RuntimeError('trace')
            def aAny(self):
                def lookBusy():
                    raise RuntimeError('trace')
                    return
                    yield
                ignored = yield lookBusy()
            def aAll(self):
                raise RuntimeError('trace')
                yield 'ignored'
            def aDo(self):
                raise RuntimeError('trace')
        root = be((Observable(),
            (Transparent(),
                (Leaf(),),
            ),
        ))

        try:
            root.call.aCall()
            self.fail('Should not happen')
        except RuntimeError:
            self.assertFunctionsOnTraceback('testTransparentUnknownImplementationIsVisibleOnTraceback', 'call_unknown', 'aCall')

        try:
            compose(root.any.aAny()).next()
            self.fail('Should not happen')
        except RuntimeError:
            self.assertFunctionsOnTraceback('testTransparentUnknownImplementationIsVisibleOnTraceback', 'any_unknown', 'aAny', 'lookBusy')

        try:
            compose(root.all.aAll()).next()
            self.fail('Should not happen')
        except RuntimeError:
            self.assertFunctionsOnTraceback('testTransparentUnknownImplementationIsVisibleOnTraceback', 'all_unknown', 'aAll')

        try:
            root.do.aDo()
            self.fail('Should not happen')
        except RuntimeError:
            self.assertFunctionsOnTraceback('testTransparentUnknownImplementationIsVisibleOnTraceback', 'do_unknown', 'aDo')

    def testFixUpExceptionTraceBack(self):
        class A:
            def a(self):
                raise Exception('A.a')
            def any_unknown(self, msg, *args, **kwargs):
                yield self.a()
        observable = Observable()
        observable.addObserver(A())
        try:
            list(compose(observable.any.a()))
        except Exception:
            self.assertFunctionsOnTraceback("testFixUpExceptionTraceBack", "a")
        else:
            self.fail('Should not happen.')

        try:
            list(compose(observable.all.a()))
        except Exception:
            self.assertFunctionsOnTraceback("testFixUpExceptionTraceBack", "a")
        else:
            self.fail('Should not happen.')

        try:
            observable.do.a()
        except Exception:
            self.assertFunctionsOnTraceback("testFixUpExceptionTraceBack", "a")
        else:
            self.fail('Should not happen.')

        try:
            observable.call.a()
        except Exception:
            self.assertFunctionsOnTraceback("testFixUpExceptionTraceBack", "a")
        else:
            self.fail('Should not happen.')

        try:
            list(compose(observable.any.unknown('a')))
        except Exception:
            self.assertFunctionsOnTraceback("testFixUpExceptionTraceBack", "a")
        else:
            self.fail('Should not happen.')

        try:
            list(compose(observable.any.somethingNotThereButHandledByUnknown('a')))
        except Exception:
            self.assertFunctionsOnTraceback("testFixUpExceptionTraceBack", "any_unknown", "a")
        else:
            self.fail('Should not happen.')

    def testMoreElaborateExceptionCleaning(self):
        class A(Observable):
            def a(self): return self.call.b()
        class B(Observable):
            def b(self): return self.call.c()
        class C(Observable):
            def c(self): return self.call.d()
        class D:
            def d(self): raise Exception('D.d')
        a = A()
        b = B()
        c = C()
        a.addObserver(b)
        b.addObserver(c)
        c.addObserver(D())
        try:
            a.a()
            self.fail('should raise exception')
        except:
            self.assertFunctionsOnTraceback("testMoreElaborateExceptionCleaning", "a", "b", "c", "d")

    def testObserverInit(self):
        initcalled = [0]
        class MyObserver(object):
            def observer_init(self):
                yield  # once is async
                initcalled[0] += 1
        root = be((Observable(), (MyObserver(),)))
        self.assertEquals([0], initcalled)
        list(compose(root.once.observer_init()))
        self.assertEquals([1], initcalled)

    def testAddObserversOnce(self):
        class MyObservable(Observable):
            pass
        o1 = MyObservable(name='O1')
        o2 = MyObservable(name='O2')
        o3 = MyObservable(name='O3')
        o4 = MyObservable(name='O4')
        o5 = MyObservable(name='O5')
        helix = \
            (o1,
                (o2, )
            )
        dna =   (o3,
                    helix,
                    (o4,),
                    (o5, helix)
                 )
        root = be(dna)
        self.assertEquals([o2], o1._observers)
        self.assertEquals([], o2._observers)
        self.assertEquals([o1, o4, o5], o3._observers)
        self.assertEquals([], o4._observers)
        self.assertEquals([o1], o5._observers)

    def testOnceAndOnlyOnce(self):
        class MyObserver(Observable):
            def methodOnlyCalledOnce(self, aList):
                aList.append('once')
                return
                yield
        once = MyObserver()
        dna = \
            (Observable(),
                (once,),
                (once,)
            )
        root = be(dna)
        collector = []
        list(compose(root.once.methodOnlyCalledOnce(collector)))
        self.assertEquals(['once'], collector)

    def testOnceCalledMethodsMustResultInAGeneratorOrComposeOrNone(self):
        callLog = []
        class MyObserver(Observable):
            def __init__(self):
                Observable.__init__(self)
                self.generatorReturningCallable = partial(lambda arg: (x for x in 'a'), arg='partialed')

            def noGeneratorFunction(self):
                callLog.append('function called')

            def valueReturningFunction(self):
                return 42

            def composedGenerator(self):
                return compose(x for x in 'a')

        once = MyObserver()
        dna = \
            (Observable(),
                (once,),
            )
        root = be(dna)
        list(compose(root.once.noGeneratorFunction()))
        self.assertEquals(['function called'], callLog)

        try:
            list(compose(root.once.valueReturningFunction()))
            self.fail("Should have gotten AssertionError because of unexpected return value")
        except AssertionError, e:
            self.assertEquals("<bound method MyObserver.valueReturningFunction of MyObserver(name=None)> returned '42'", str(e))

        try:
            result = list(compose(root.once.composedGenerator()))
            self.assertEquals(['a'], result)
        except AssertionError, e:
            self.fail('Should not fail: %s' % e)

        try:
            result = list(compose(root.once.generatorReturningCallable()))
            self.assertEquals(['a'], result)
        except AssertionError, e:
            self.fail('Should not fail: %s' % e)

    def testOnceInDiamondWithTransparent(self):
        class MyObserver(Observable):
            def methodOnlyCalledOnce(self, aList):
                aList.append('once')
                return
                yield
        once = MyObserver()
        diamond = \
            (Transparent(),
                (Transparent(),
                    (once,)
                ),
                (Transparent(),
                    (once,)
                )
            )
        root = be(diamond)
        collector = []
        list(compose(root.once.methodOnlyCalledOnce(collector)))
        self.assertEquals(['once'], collector)

    def testPropagateThroughAllObservablesInDiamondWithNONTransparentObservablesWithoutUnknownMethodDelegatingUnknownCalls(self):
        class MyObserver(Observable):
            def methodOnlyCalledOnce(self, aList):
                aList.append('once')
                return
                yield
        once = MyObserver()
        diamond = \
            (Observable(),
                (Observable(),
                    (once,)
                ),
                (Observable(),
                    (once,)
                )
            )
        root = be(diamond)
        collector = []
        list(compose(root.once.methodOnlyCalledOnce(collector)))
        self.assertEquals(['once'], collector)

    def testNonObservableInTreeWithOnce(self):
        class MyObserver(object):
            def methodOnNonObservableSubclass(self, aList):
                aList.append('once')
                return
                yield
        once = MyObserver()
        dna =   (Observable(),
                    (once,)
                )
        root = be(dna)
        collector = []
        list(compose(root.once.methodOnNonObservableSubclass(collector)))
        self.assertEquals(['once'], collector)

    def testOnceAndOnlyOnceForMutuallyObservingObservables(self):
        class MyObserver(Observable):
            def methodOnlyCalledOnce(self, aList):
                aList.append(self)
                return
                yield
        ownobserverobserver = MyObserver()
        dna = \
            (Observable(),
                (ownobserverobserver,
                    (Observable("observer"),
                        (ownobserverobserver,),
                    )
                )
            )
        root = be(dna)
        collector = []
        list(compose(root.once.methodOnlyCalledOnce(collector)))
        self.assertEquals([ownobserverobserver], collector)

    def testOnceInternalsNotOnTracebackUnlessAssertsAndThenOnlyOnce(self):
        class OnceRaiser(object):
            def raisesOnCall(self):
                raise BaseException('Boom')
            def raisesOnCallGenerator(self):
                raise BaseException('Ka-Boom')
                yield

        dna = (Observable(),              # called-from
            (Observable(),                # 1
                (Observable(),            # 2
                    (Observable(),        # 3
                        (OnceRaiser(),),  # target
                    )
                )
            )
        )
        root = be(dna)

        try:
            list(compose(root.once.raisesOnCallGenerator()))
        except BaseException:
            self.assertFunctionsOnTraceback('testOnceInternalsNotOnTracebackUnlessAssertsAndThenOnlyOnce', 'raisesOnCallGenerator')
        else:
            self.fail('Should not happen')

        try:
            list(compose(root.once.raisesOnCall()))
        except BaseException:
            self.assertFunctionsOnTraceback('testOnceInternalsNotOnTracebackUnlessAssertsAndThenOnlyOnce', 'raisesOnCall')
        else:
            self.fail('Should not happen')

    @skip_if(cextension)
    def testNonGeneratorMethodMayNeverRaiseGeneratorExceptionsOnMessages(self):
        # any, all, do, call and once
        class OddObject(object):
            def stopIter(self):
                raise StopIteration('Stop!')
            def genExit(self):
                raise GeneratorExit('Exit!')

        dna = (Observable(),
            (Transparent(),
                (OddObject(),),
            )
        )
        root = be(dna)

        # Verify traceback's and wrapped-exception text is ok
        try: root.call.stopIter()
        except AssertionError, e:
            self.assertTrue(str(e).startswith('Non-Generator <bound method OddObject.stopIter of <core.observabletest.OddObject object at 0x'), str(e))
            expected = ignoreLineNumbers('''>> should not have raised Generator-Exception:
Traceback (most recent call last):
  File "%(__file__)s", line [#], in stopIter
    raise StopIteration('Stop!')
StopIteration: Stop!
''' % fileDict)
            self.assertTrue(ignoreLineNumbers(str(e)).endswith(expected), str(e))
            self.assertFunctionsOnTraceback(
                'testNonGeneratorMethodMayNeverRaiseGeneratorExceptionsOnMessages',
                'call_unknown',  # From Transparent, is supposed to be on the stack to aid retracing the path taken for a messages.
                'handleNonGeneratorGeneratorExceptions')
        else: self.fail('Should not happen')

        try: root.call.genExit()
        except AssertionError, e:
            self.assertTrue(str(e).startswith('Non-Generator <bound method OddObject.genExit of <core.observabletest.OddObject object at 0x'), str(e))
            expected = ignoreLineNumbers('''>> should not have raised Generator-Exception:
Traceback (most recent call last):
  File "%(__file__)s", line [#], in genExit
    raise GeneratorExit('Exit!')
GeneratorExit: Exit!
''' % fileDict)
            self.assertTrue(ignoreLineNumbers(str(e)).endswith(expected), str(e))
            self.assertFunctionsOnTraceback(
                'testNonGeneratorMethodMayNeverRaiseGeneratorExceptionsOnMessages',
                'call_unknown',  # From Transparent, is supposed to be on the stack to aid retracing the path taken for a messages.
                'handleNonGeneratorGeneratorExceptions')
        else: self.fail('Should not happen')

        # Verify logic implemented in all messages, with traceback-manipulation
        for observableCallName, failMethod in [
                    ('do', 'stopIter'),
                    ('do', 'genExit'),
                    ('any', 'stopIter'),
                    ('any', 'genExit'),
                    ('all', 'stopIter'),
                    ('all', 'genExit'),
                    ('once', 'stopIter'),
                    ('once', 'genExit'),
                ]:
            try:
                _ = getattr(getattr(root, observableCallName), failMethod)()
                if observableCallName != 'do':
                    list(compose(_))
            except AssertionError, e:
                self.assertTrue('should not have raised Generator-Exception:' in str(e), str(e))
                expected = [
                    'testNonGeneratorMethodMayNeverRaiseGeneratorExceptionsOnMessages',
                    'handleNonGeneratorGeneratorExceptions',
                ]
                if observableCallName != 'once':
                    expected[1:1] = '%s_unknown' % observableCallName,  # From Transparent, is supposed to be on the stack to aid retracing the path taken for a messages.
                self.assertFunctionsOnTraceback(*expected)
            else: self.fail('Should not happen')

    def testNoLeakingGeneratorsInCycle(self):
        class Responder(Observable):
            def message(self):
                yield 'response'
        obs = Observable()
        obs.addObserver(Responder())
        result = compose(obs.all.message()).next()
        self.assertEquals('response',result)
        del obs

    def testNoLeakingGeneratorsInMultiTransparents(self):
        class Responder(Observable):
            def message(self):
                return 'response'
        obs = Observable()
        t1 = Transparent()
        t2 = Transparent()
        obs.addObserver(t1)
        t1.addObserver(t2)
        t2.addObserver(Responder())
        result = obs.call.message()
        self.assertEquals('response', result)
        del obs, t1, t2, result

    def testMatchingBasedOnDefaultArgs(self):
        class A(object):
            def a(x, y=10, z=11):
                p = 1
                q = 2
                yield
        a = A()
        func = a.a
        code = func.func_code
        func_defaults = func.func_defaults
        self.assertEquals((10,11), func_defaults)
        argcount = code.co_argcount
        self.assertEquals(3, argcount)
        varnames = code.co_varnames
        self.assertEquals(('x', 'y', 'z', 'p', 'q'), varnames)
        argnames = varnames[:argcount]
        self.assertEquals(('x','y','z'), argnames)
        kwargsnames = argnames[-len(func_defaults):]
        self.assertEquals(('y','z'), kwargsnames)
        kwargdefaults = dict(zip(kwargsnames, func_defaults))
        self.assertEquals({'y':10, 'z':11}, kwargdefaults)
        self.assertEquals({'z':11, 'y':10}, kwargdefaults)
        func.__dict__['kwargdefaults'] = kwargdefaults
        self.assertEquals({'z':11, 'y':10}, func.kwargdefaults)

        class Wildcard(object):
            def __eq__(self, other):
                return True
        self.assertTrue({'z':11, 'y':10} == {'z':11, 'y': Wildcard()})

    def testTransparentInCaseNoneOfTheObserversRespond(self):
        root = be((Observable(),
            (Transparent(),),
            (Transparent(),
                (Transparent(),
                   (object(),)
                ),
            ),
            (Responder(42),),
        ))

        self.assertEquals(42, root.call.m())

        try:
            g = compose(root.any.m())
            self.assertEquals(42, g.next())
            g.next()
            self.fail("Should have raised StopIteration")
        except StopIteration, e:
            self.assertEquals((42,), e.args)

    def testObserverAttributeErrorNotIgnored(self):
        class GetAttr(object):
            def __init__(self, attrName):
                self.attrName = attrName
            def call_unknown(self, message, *args, **kwargs):
                return getattr(self, self.attrName)
            def any_unknown(self, message, *args, **kwargs):
                raise StopIteration(getattr(self, self.attrName))
                yield

        root = be((Observable(),
            (Transparent(),
                (GetAttr('doesnotexist'),)
            ),
            (GetAttr('__class__'),)
        ))
    
        try:
            result = root.call.someMessage()
            self.fail("should not get here: %s" % result)
        except AttributeError, e:
            self.assertEquals("'GetAttr' object has no attribute 'doesnotexist'", str(e))

        try:
            list(compose(root.any.someMessage()))
            self.fail("should not get here")
        except AttributeError, e:
            self.assertEquals("'GetAttr' object has no attribute 'doesnotexist'", str(e))

    def testThrow(self):
        class A(Observable):
            def f1(self):
                yield "A:f1-1"
                yield "A:f1-2"
                yield "A:f1-3"
        class B(Observable):
            def f1(self):
                yield "B:f1-1"
                yield "B:f1-2"
                yield "B:f1-3"
        root = Observable()
        root.addObserver(A())
        root.addObserver(B())
        g = compose(root.all.f1())
        g.next()
        r = g.throw(DeclineMessage)
        self.assertEquals("B:f1-1", r)

    def testRaisingDeclineMessageResultsInCallOnNextObservable(self):
        class SemiTransparent(Observable):
            def call_unknown(self, message, *args, **kwargs):
                if message == 'theMessage':
                    return self.call.unknown(message, *args, **kwargs)
                raise DeclineMessage

            def any_unknown(self, message, *args, **kwargs):
                if message == 'theMessage':
                    value = yield self.any.unknown(message, *args, **kwargs)
                    raise StopIteration(value)
                raise DeclineMessage
        
        root = be((Observable(),
            (SemiTransparent(),
                (Responder(41),)
            ),
            (Responder(42),)
        ))

        self.assertEquals([42], list(compose(root.any.message())))
        self.assertEquals(42, root.call.anotherMessage())

    def testRaisingDeclineMessageFromAllMakesNoDifference(self):
        class SemiTransparent(Observable):
            def all_unknown(self, message, *args, **kwargs):
                if message == 'theMessage':
                    yield self.all.unknown(message, *args, **kwargs)
                raise DeclineMessage
        
        root = be((Observable(),
            (SemiTransparent(),
                (Responder(41),)
            ),
            (Responder(42),)
        ))

        self.assertEquals([41, 42], list(compose(root.all.theMessage())))
        self.assertEquals([42], list(compose(root.all.message())))

    def testRaisingDeclineMessageFromDoMakesNoDifference(self):
        class SemiTransparent(Observable):
            def do_unknown(self, message, *args, **kwargs):
                if message == 'theMessage':
                    self.do.unknown(message, *args, **kwargs)
                raise DeclineMessage
        
        observer1 = CallTrace('observer1')
        observer2 = CallTrace('observer2')
        root = be((Observable(),
            (SemiTransparent(),
                (observer1,)
            ),
            (observer2,)
        ))

        root.do.theMessage()
        self.assertEquals(['theMessage'], [m.name for m in observer1.calledMethods])
        self.assertEquals(['theMessage'], [m.name for m in observer2.calledMethods])

        observer1.calledMethods.reset()
        observer2.calledMethods.reset()
        root.do.message()
        self.assertEquals([], [m.name for m in observer1.calledMethods])
        self.assertEquals(['message'], [m.name for m in observer2.calledMethods])

    def testDeferredObjectsAreCached(self):
        class A(object):
            def a(self):
                pass
        observable = Observable()
        observable.addObserver(A())
        f1 = observable.all.f
        f2 = observable.all.f
        self.assertEquals(f1, f2)

    def testRebuildDefersAfterAddObserver(self):
        observable = Observable()
        called = []
        class A(Observable):
            def method(this):
                called.append("A")
                return
                yield
        class B(Observable):
            def method(this):
                called.append("B")
                return
                yield
        observable.addObserver(A())
        list(compose(observable.all.method()))
        self.assertEquals(['A'], called)
        del called[:]
        observable.addObserver(B())
        list(compose(observable.all.method()))
        self.assertEquals(['A', 'B'], called)

    def xxtestRelativeSpeedOfAll(self):
        from time import time
        class A(Observable):
            def f(self):
                raise StopIteration(None)
                yield
        root = Observable()
        connector = Transparent()
        root.addObserver(connector)
        connector.addObserver(A())
        connector.addObserver(A())
        connector.addObserver(A())
        connector.addObserver(A())
        connector.addObserver(A())
        connector.addObserver(A())
        connector.addObserver(A())
        t = 0.0
        for _ in xrange(10000):
            g = compose(root.all.f())
            t0 = time()
            for _ in g:
                g.next()
            t1 = time()
            t += t1 - t0
        print t

        def f():
            for _ in xrange(10000):
                g = compose(root.all.f())
                for _ in g:
                    g.next()
        #from hotshot import Profile
        #p = Profile("profile.prof", lineevents=1, linetimings=1)
        #p.runcall(f)

    def assertFunctionsOnTraceback(self, *args):
        na, na, tb = exc_info()
        for functionName in args:
            self.assertEquals(functionName, tb.tb_frame.f_code.co_name)
            tb = tb.tb_next
        self.assertEquals(None, tb, format_tb(tb))

    def get_tracked_objects(self):
        return [o for o in gc.get_objects() if type(o) in 
                (compose, GeneratorType, Exception,
                    AllMessage, AnyMessage, DoMessage, OnceMessage)]
 
    def setUp(self):
        gc.collect()
        self._baseline = self.get_tracked_objects()

    def tearDown(self):
        def tostr(o):
            if isframe(o):
                return getframeinfo(o)
            try:
                return tostring(o)
            except:
                return repr(o)
        gc.collect()
        diff = set(self.get_tracked_objects()) - set(self._baseline)
        self.assertEquals(set(), diff)
        for obj in diff:
            print "Leak:"
            print tostr(obj)
            print "Referrers:"
            for o in gc.get_referrers(obj):
                print tostr(o)
        del self._baseline
        gc.collect()


class Responder(Observable):
    def __init__(self, value):
        self._value = value
    def any_unknown(self, message, *args, **kwargs):
        yield self._value
        raise StopIteration(self._value)
    def call_unknown(self, message, *args, **kwargs):
        return self._value
    def all_unknown(self, message, *args, **kwargs):
        yield self._value


from re import sub
def ignoreLineNumbers(s):
    return sub("line \d+,", "line [#],", s)

