import unittest
import struct
import hashlib
from tools.inspect_wheel_materials import package_pins, elf_text_hash


class WheelMaterials(unittest.TestCase):
    def test_elf_reader_never_loads_native_code(self):
        header=bytearray(64);header[:6]=b'\x7fELF\x02\x01'
        struct.pack_into('<Q',header,40,64)
        struct.pack_into('<HHH',header,58,64,3,1)
        names=b'\0.shstrtab\0.text\0';payload=b'not executable test bytes'
        empty=bytes(64)
        strings=struct.pack('<IIQQQQIIQQ',1,3,0,0,256,len(names),0,0,1,0)
        text=struct.pack('<IIQQQQIIQQ',11,1,0,0,256+len(names),len(payload),0,0,1,0)
        self.assertEqual(elf_text_hash(bytes(header)+empty+strings+text+names+payload),hashlib.sha256(payload).hexdigest())
        with self.assertRaises(ValueError):elf_text_hash(bytes(header))

    def test_reads_literals_without_executing_source(self):
        source = "raise RuntimeError('must never execute')\np=Package(name='demo',source_url='https://github.com/a/demo.tar.gz',sha256='" + 'a'*64 + "')"
        self.assertEqual(package_pins(source)[0]['package'], 'demo')

    def test_dynamic_source_is_not_evaluated(self):
        with self.assertRaises(ValueError):
            package_pins("p=Package(name='demo',source_url=discover(),sha256='pin')")
