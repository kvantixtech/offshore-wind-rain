"""Read members of a remote zip file with HTTP range requests, without downloading the whole archive."""
import io, urllib.request

class RangeFile(io.RawIOBase):
    def __init__(self, url, ua, block=1 << 20):
        self.url, self.ua, self.pos, self.block = url, ua, 0, block
        req = urllib.request.Request(url, headers={"User-Agent": ua}, method="HEAD")
        with urllib.request.urlopen(req, timeout=120) as r:
            self.size = int(r.headers["Content-Length"])
            self.ranges = r.headers.get("Accept-Ranges")
        self.fetched = 0
        self._cache = (None, b"")
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos
    def _get(self, start, end):
        req = urllib.request.Request(self.url, headers={"User-Agent": self.ua, "Range": f"bytes={start}-{end}"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    b = r.read()
                self.fetched += len(b)
                return b
            except Exception:
                if attempt == 4: raise
    def read(self, n=-1):
        if n is None or n < 0: n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0: return b""
        cs, cb = self._cache
        if cs is not None and cs <= self.pos and self.pos + n <= cs + len(cb):
            out = cb[self.pos - cs:self.pos - cs + n]
        else:
            want = max(n, self.block)
            end = min(self.size - 1, self.pos + want - 1)
            cb = self._get(self.pos, end); self._cache = (self.pos, cb)
            out = cb[:n]
        self.pos += len(out)
        return out
    def readinto(self, b):
        d = self.read(len(b)); b[:len(d)] = d; return len(d)
