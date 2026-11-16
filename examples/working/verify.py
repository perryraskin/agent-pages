"""Check published gallery metadata, local documentation links and showcase preservation."""
from pathlib import Path
import re
import struct
import hashlib
import zlib
ROOT = Path(__file__).resolve().parents[2]
p = ROOT / 'docs/images/working-states.png'
data = p.read_bytes()
assert data[:8] == b'\x89PNG\r\n\x1a\n'
assert len(data) < 1500000
pos, chunks = 8, []
while pos < len(data):
    n = struct.unpack('>I', data[pos:pos+4])[0]
    kind = data[pos+4:pos+8]
    assert kind in (b'IHDR', b'IDAT', b'IEND', b'PLTE', b'tRNS'), kind
    assert zlib.crc32(data[pos+4:pos+8+n]) == struct.unpack('>I',data[pos+8+n:pos+12+n])[0]
    chunks.append(kind.decode())
    if kind == b'IHDR':
        assert struct.unpack('>II', data[pos+8:pos+16]) == (2700, 2020)
    pos += n + 12
assert pos == len(data) and chunks[-1] == 'IEND'
for doc in [ROOT/'README.md', ROOT/'examples/working/README.md']:
    for link in re.findall(r'\]\(([^)]+)\)', doc.read_text()):
        if '://' not in link and not link.startswith('#'):
            assert (doc.parent/link.split('#')[0]).exists(), (doc, link)
# The original three-phone showcase must remain byte-for-byte identical.
assert hashlib.sha256((ROOT/'docs/images/showcase.png').read_bytes()).hexdigest() == 'b7187d0cf4d530639ca8ffbf6bc8816d2457c569e4f7673a7397e1c16413a604'
print(f'PASS gallery {len(data)} bytes; 2700×2020; chunks {chunks}; local links resolve; original showcase unchanged.')
