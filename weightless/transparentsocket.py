class TransparentSocket(object):
    def __init__(self, originalObject, logFile = None):
        self._originalObject = originalObject
        self._logFile = logFile

    def __getattr__(self, attrname):
        return self._originalObject.__getattr__(attrname)

    def _logString(self, aString):
        if self._logFile:
            f = open(self._logFile, 'a')
            try:
                f.write(aString + "\n")
            finally:
                f.close()

    def recv(self, *args, **kwargs):
        result = self._originalObject.recv(*args, **kwargs)
        self._logString('recv(%s, %s) -> "%s"' % (args, kwargs, result))
        return result

    def send(self, *args, **kwargs):
        result = self._originalObject.send(*args, **kwargs)
        self._logString("send(%s, %s) -> %s" % (args, kwargs, result))
        return result

    def sendall(self, *args, **kwargs):
        self._logString("sendall(%s, %s)" % (args, kwargs))
        return self._originalObject.sendall(*args, **kwargs)
