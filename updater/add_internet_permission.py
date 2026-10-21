#!/usr/bin/env python3
"""Add <uses-permission android:name="android.permission.INTERNET"/> to a
binary AndroidManifest.xml (AXML), preserving all existing content.

Technique: append new strings to the string pool (existing indices keep
their meaning because string offsets are relative to stringsStart, which
grows by exactly the size of the added offset entries), then insert a
start/end element pair for uses-permission right before <uses-sdk>.
"""
import struct
import sys

SRC, DST = sys.argv[1], sys.argv[2]
PERM = "android.permission.INTERNET"
ELEM = "uses-permission"
URI = "http://schemas.android.com/apk/res/android"

data = bytearray(open(SRC, "rb").read())
magic, _fsize = struct.unpack_from("<II", data, 0)
assert magic == 0x00080003, "not an AXML file"

# ---- walk chunks -------------------------------------------------------
off = 8
pool_info = None
chunk_list = []
while off < len(data):
    ctype, hsize, csize = struct.unpack_from("<HHI", data, off)
    chunk_list.append((ctype, off, csize))
    if ctype == 0x0001:
        pool_info = (off, hsize, csize)
    off += csize
assert pool_info, "no string pool"
poff, phsize, psize = pool_info

scount, stylecount, flags, sstart, styles_start = struct.unpack_from(
    "<IIIII", data, poff + 8)
assert stylecount == 0, "styled string pool not supported"
is_utf8 = bool(flags & 0x100)
offsets_pos = poff + phsize


def get_string(i):
    o = struct.unpack_from("<I", data, offsets_pos + 4 * i)[0]
    p = poff + sstart + o
    if is_utf8:
        def rl(p):
            b = data[p]
            if b & 0x80:
                return ((b & 0x7F) << 8) | data[p + 1], p + 2
            return b, p + 1
        _clen, p = rl(p)
        blen, p = rl(p)
        return bytes(data[p:p + blen]).decode("utf-8")
    ln = struct.unpack_from("<H", data, p)[0]
    p += 2
    if ln & 0x8000:
        ln2 = struct.unpack_from("<H", data, p)[0]
        p += 2
        ln = ((ln & 0x7FFF) << 16) | ln2
    return bytes(data[p:p + 2 * ln]).decode("utf-16-le")


strings = [get_string(i) for i in range(scount)]


def find(s):
    return strings.index(s) if s in strings else -1


uri_idx = find(URI)
name_idx = find("name")
assert uri_idx >= 0 and name_idx >= 0, "namespace/name strings missing"

# ---- encode strings to append ------------------------------------------
def enc(s):
    if is_utf8:
        b = s.encode("utf-8")
        def el(n):
            if n < 0x80:
                return bytes([n])
            return bytes([0x80 | (n >> 8), n & 0xFF])
        return el(len(s)) + el(len(b)) + b + b"\x00"
    b = s.encode("utf-16-le")
    return struct.pack("<H", len(s)) + b + b"\x00\x00"


new_strings = []
perm_idx = find(PERM)
if perm_idx < 0:
    perm_idx = scount + len(new_strings)
    new_strings.append(PERM)
elem_idx = find(ELEM)
if elem_idx < 0:
    elem_idx = scount + len(new_strings)
    new_strings.append(ELEM)

n_new = len(new_strings)
# byte offset (relative to strings data start) where appended data begins
strings_data_len = psize - sstart
new_offsets = []
blob = b""
cursor = strings_data_len
for s in new_strings:
    e = enc(s)
    new_offsets.append(cursor)
    blob += e
    cursor += len(e)

# ---- rebuild string pool chunk -----------------------------------------
growth = 4 * n_new
new_psize = psize + growth + len(blob)
new_pool = bytearray()
new_pool += struct.pack("<HHI", 0x0001, phsize, new_psize)
new_pool += struct.pack("<IIIII", scount + n_new, stylecount, flags,
                        sstart + growth, styles_start + growth if styles_start else 0)
new_pool += bytes(data[poff + 28: poff + phsize])  # rest of header (if any)
for i in range(scount):
    new_pool += struct.pack("<I", struct.unpack_from("<I", data, offsets_pos + 4 * i)[0])
for o in new_offsets:
    new_pool += struct.pack("<I", o)
new_pool += bytes(data[poff + sstart: poff + psize])  # old string data
new_pool += blob
assert len(new_pool) == new_psize, (len(new_pool), new_psize)

# ---- build uses-permission element chunks -------------------------------
line = 6
start_el = struct.pack("<HHI", 0x0102, 16, 56)
start_el += struct.pack("<iI", line, 0xFFFFFFFF)          # lineNumber, comment
start_el += struct.pack("<iI", -1, elem_idx)              # ns, name
start_el += struct.pack("<HHHHHH", 20, 20, 1, 0, 0, 0)    # attrStart..styleIndex
start_el += struct.pack("<iI", uri_idx, name_idx)         # attr ns, name
start_el += struct.pack("<I", perm_idx)                   # rawValue
start_el += struct.pack("<HBBI", 8, 0, 0x03, perm_idx)    # typedValue: STRING
assert len(start_el) == 56

end_el = struct.pack("<HHI", 0x0103, 16, 24)
end_el += struct.pack("<iI", line, 0xFFFFFFFF)
end_el += struct.pack("<iI", -1, elem_idx)
assert len(end_el) == 24

# ---- locate insertion point: start of the <uses-sdk> start element ----
insert_at = None
for ctype, coff, csize in chunk_list:
    if ctype == 0x0102:
        nm = struct.unpack_from("<I", data, coff + 20)[0]
        if get_string(nm) == "uses-sdk":
            insert_at = coff
            break
assert insert_at is not None, "uses-sdk element not found"
assert insert_at > poff + psize, "insertion point must be after string pool"

# ---- assemble new file ---------------------------------------------------
delta = new_psize - psize
out = bytearray()
out += bytes(data[:8])                       # header (size patched below)
out += new_pool
out += bytes(data[poff + psize: insert_at])  # chunks between pool and uses-sdk
out += start_el + end_el
out += bytes(data[insert_at:])
struct.pack_into("<I", out, 4, len(out))
open(DST, "wb").write(bytes(out))
print(f"OK: {len(data)} -> {len(out)} bytes; perm_idx={perm_idx} elem_idx={elem_idx} "
      f"uri_idx={uri_idx} name_idx={name_idx}; utf8={is_utf8}; strings {scount}->{scount + n_new}")
