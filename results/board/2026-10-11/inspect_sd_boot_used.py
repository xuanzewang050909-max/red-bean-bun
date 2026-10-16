from pathlib import Path
import hashlib
import json
import re
import shutil
import struct
import sys

sys.stdout.reconfigure(encoding='utf-8')
source = Path('F:/')
out = Path('D:/PLD/retina_fpga/results/board/2026-10-11')
backup = out / 'sd_boot_backup'
backup.mkdir(parents=True, exist_ok=True)

def fdt_props(data):
    header = struct.unpack_from('>10I', data)
    magic, total, structs, strings, _, version, _, _, stringsize, structsize = header
    if magic != 0xd00dfeed or total > len(data):
        raise ValueError('Invalid FDT header')
    names = data[strings:strings + stringsize]
    pos, stack, props = structs, [], {}
    while pos < structs + structsize:
        token, = struct.unpack_from('>I', data, pos)
        pos += 4
        if token == 1:
            end = data.index(b'\0', pos)
            stack.append(data[pos:end].decode('utf-8', errors='replace'))
            pos = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from('>II', data, pos)
            pos += 8
            end = names.index(b'\0', nameoff)
            name = names[nameoff:end].decode()
            path = '/' + '/'.join(stack[1:])
            props.setdefault(path, {})[name] = data[pos:pos + length]
            pos = (pos + length + 3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            break
        else:
            raise ValueError(f'Unknown FDT token {token}')
    return props

def readable(value, name=''):
    binary_names = ('reg', 'ranges', '#address-cells', '#size-cells', 'port-number', 'interrupts', 'clocks', 'phandle', 'linux,phandle', 'load', 'entry', 'timestamp', 'value', 'interrupt-parent', 'phy-handle', 'enet-reset', 'local-mac-address', 'xlnx,ptp-enet-clock')
    if name not in binary_names and value.endswith(b'\0') and any(32 <= b <= 126 for b in value) and all(32 <= b <= 126 or b == 0 for b in value):
        return value.rstrip(b'\0').decode('ascii').split('\0')
    return value.hex() if len(value) <= 48 else f'<{len(value)} bytes>'

report = {'operation': 'Read-only source; boot-file copies only, NOT a full-card backup', 'files': []}
for name in ('BOOT.BIN', 'image.ub', 'system.bit', 'system.dtb', 'u-boot.bin', 'zImage'):
    src, dst = source / name, backup / name
    content = src.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if dst.exists() and hashlib.sha256(dst.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f'Existing backup differs: {dst}')
    if not dst.exists():
        shutil.copy2(src, dst)
    if hashlib.sha256(dst.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Backup hash mismatch')
    report['files'].append({'name': name, 'size': len(content), 'sha256': digest})

tree = fdt_props((backup / 'system.dtb').read_bytes())
report['device_tree'] = {p: {k: readable(v, k) for k, v in attrs.items()} for p, attrs in tree.items()
    if p in ('/', '/chosen', '/aliases') or any(s in p for s in ('serial@', 'uart@', 'memory@', '/memory', 'ethernet@'))}
fit = fdt_props((backup / 'image.ub').read_bytes())
report['fit_image'] = {p: {k: readable(v, k) for k, v in attrs.items() if k != 'data'} for p, attrs in fit.items()}
embedded = fdt_props(fit['/images/fdt@system-top.dtb']['data'])
report['fit_embedded_device_tree'] = {p: {k: readable(v, k) for k, v in attrs.items()} for p, attrs in embedded.items()
    if p in ('/', '/chosen', '/aliases', '/memory') or 'serial@' in p}
report['memory_bytes'] = struct.unpack('>II', tree['/memory']['reg'])[1]
bit = (backup / 'system.bit').read_bytes()
pos = 2 + struct.unpack_from('>H', bit)[0]
pos += 2
bit_header = {}
while True:
    key = chr(bit[pos])
    pos += 1
    if key == 'e':
        length, = struct.unpack_from('>I', bit, pos)
        pos += 4
        payload = bit[pos:pos + length]
        bit_header['payload_bytes'] = length
        break
    length, = struct.unpack_from('>H', bit, pos)
    pos += 2
    bit_header[key] = bit[pos:pos + length].rstrip(b'\0').decode('ascii')
    pos += length
report['system_bit_header'] = bit_header
boot = (backup / 'BOOT.BIN').read_bytes()
raw_offset = boot.find(payload)
swapped_payload = bytearray(payload)
for i in range(0, len(payload), 4):
    swapped_payload[i:i+4] = payload[i:i+4][::-1]
swapped_offset = boot.find(swapped_payload)
report['boot_bin_bit_payload_match'] = {'raw_offset': raw_offset, 'word_byte_reversed_offset': swapped_offset,
    'interpretation': 'Exact match proves system.bit payload is included in BOOT.BIN' if max(raw_offset, swapped_offset) >= 0 else 'No exact payload match found; BOOT.BIN target not established by this check'}
for name in ('BOOT.BIN', 'u-boot.bin', 'system.bit'):
    strings = [m.decode('ascii') for m in re.findall(rb'[\x20-\x7e]{6,}', (backup / name).read_bytes())]
    selected = [s for s in strings if re.search(r'U-Boot|Xilinx|PYNQ|Pynq|Zed[Bb]oard|[Zz]ynq|ttyPS|bootargs=|bootcmd=|xc7z|\.ncd|\.bit', s)]
    report[name + '_selected_strings'] = selected[:80]
(out / 'sd_boot_inspection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
