import threading
import time
import struct
import sys

try:
    import pymem
    import pymem.process
except ImportError:
    pymem = None

PROCESS_NAME = "eu07.exe"
TARGET_LOG_STRING = b"motiontelemetry: socket send failed"


class MaszynaHook:
    def __init__(self):
        self.current_speed_kmh = None
        self.is_connected = False
        self.error_message = ""
        self.status_message = "Waiting for simulator..."
        self._running = True

        if pymem is None:
            self.error_message = "pymem not installed"
            self.status_message = "Error: pymem not installed"
            self._running = False
            return

        if sys.platform != "win32":
            self.error_message = "MaSzyna hook is only supported on Windows"
            self.status_message = "Error: Unsupported platform (requires Windows)"
            self._running = False
            return

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if hasattr(self, '_thread') and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _read_u64(self, pm, address):
        return pm.read_ulonglong(address)

    def _read_double(self, pm, address):
        return pm.read_double(address)

    def _get_module_info(self, pm, module_name):
        for module in pymem.process.enum_process_module(pm.process_handle):
            if module.name.lower() == module_name.lower():
                return module.lpBaseOfDll, module.SizeOfImage
        return None, None

    def _scan_pattern(self, pm, base, size, pattern):
        chunk_size = 0x10000
        pat_len = len(pattern)
        results = []
        for offset in range(0, size - pat_len, chunk_size):
            read_size = min(chunk_size + pat_len - 1, size - offset)
            try:
                chunk = pm.read_bytes(base + offset, read_size)
            except Exception:
                continue

            idx = 0
            while True:
                idx = chunk.find(pattern, idx)
                if idx == -1:
                    break
                results.append(base + offset + idx)
                idx += 1
        return results

    def _extract_rip_relative_address(self, pm, instruction_addr, instruction_len=7):
        disp_bytes = pm.read_bytes(instruction_addr + 3, 4)
        disp = struct.unpack('<i', disp_bytes)[0]
        return instruction_addr + instruction_len + disp

    def _find_log_string_reference(self, pm, base, size):
        string_addrs = self._scan_pattern(pm, base, size, TARGET_LOG_STRING)
        if not string_addrs:
            return None

        string_addr = string_addrs[0]

        for offset in range(0, size - 7, 0x10000):
            try:
                chunk = pm.read_bytes(base + offset, min(0x10000 + 7, size - offset))
            except Exception:
                continue

            for i in range(len(chunk) - 7):
                if chunk[i] in (0x48, 0x4C) and chunk[i + 1] == 0x8D:
                    disp = struct.unpack('<i', chunk[i + 3:i + 7])[0]
                    target = base + offset + i + 7 + disp
                    if target == string_addr:
                        return base + offset + i

        return None

    def _read_function_body(self, pm, base, lea_addr):
        scan_start = max(base, lea_addr - 0x800)
        scan_size = lea_addr - scan_start + 0x100
        try:
            func_bytes = pm.read_bytes(scan_start, scan_size)
            return scan_start, func_bytes
        except Exception:
            return None, None

    def _find_train_global_candidates(self, pm, scan_start, func_bytes):
        candidates = []
        for i in range(len(func_bytes) - 15):
            if func_bytes[i] == 0x48 and func_bytes[i + 1] == 0x8B:
                modrm = func_bytes[i + 2]
                if (modrm & 0xC7) == 0x05:
                    actual_addr = scan_start + i
                    global_addr = self._extract_rip_relative_address(pm, actual_addr, 7)

                    if i + 11 < len(func_bytes):
                        if func_bytes[i + 7] == 0x48 and func_bytes[i + 8] == 0x85:
                            test_reg = func_bytes[i + 9]
                            if (test_reg & 0xC0) == 0xC0 and (test_reg & 7) == ((test_reg >> 3) & 7):
                                if func_bytes[i + 10] == 0x74 or (
                                        func_bytes[i + 10] == 0x0F and func_bytes[i + 11] == 0x84):
                                    reg_code = (modrm >> 3) & 7
                                    candidates.append((actual_addr, global_addr, reg_code))
        return candidates

    def _trace_pointer_loads(self, func_bytes, start_idx, reg_train):
        ptr_registers = {}
        i = start_idx
        while i < len(func_bytes) - 4:
            prefix = func_bytes[i]
            if (prefix & 0xF0) == 0x40 and func_bytes[i + 1] == 0x8B:
                modrm = func_bytes[i + 2]
                mod = (modrm >> 6) & 3
                rm = modrm & 7
                reg_dest = ((modrm >> 3) & 7) + (8 if (prefix & 4) else 0)
                reg_base = rm + (8 if (prefix & 1) else 0)

                if reg_base == reg_train:
                    offset = None
                    inst_len = 3
                    if mod == 1:
                        offset = func_bytes[i + 3]
                        if offset >= 128: offset -= 256
                        inst_len = 4
                    elif mod == 2:
                        offset = struct.unpack('<i', func_bytes[i + 3:i + 7])[0]
                        inst_len = 7

                    if offset is not None and offset > 0:
                        if offset not in ptr_registers:
                            ptr_registers[offset] = set()
                        ptr_registers[offset].add(reg_dest)
                        i += inst_len
                        continue
            i += 1
        return ptr_registers

    def _trace_double_accesses(self, func_bytes, start_idx, ptr_registers):
        member_accesses = {offset: set() for offset in ptr_registers}
        i = start_idx

        while i < len(func_bytes) - 4:
            if func_bytes[i] == 0xF2:
                rex = 0
                idx = i + 1
                if (func_bytes[idx] & 0xF0) == 0x40:
                    rex = func_bytes[idx]
                    idx += 1

                if func_bytes[idx] == 0x0F:
                    modrm = func_bytes[idx + 2]
                    mod = (modrm >> 6) & 3
                    rm = modrm & 7
                    reg_base = rm + (8 if (rex & 1) else 0)

                    if mod == 2:
                        disp = struct.unpack('<i', func_bytes[idx + 3:idx + 7])[0]
                        for offset_occ, regs in ptr_registers.items():
                            if reg_base in regs:
                                member_accesses[offset_occ].add(disp)

            elif func_bytes[i] == 0x0F and func_bytes[i + 1] == 0x10:
                modrm = func_bytes[i + 2]
                mod = (modrm >> 6) & 3
                rm = modrm & 7
                reg_base = rm

                if mod == 2:
                    disp = struct.unpack('<i', func_bytes[i + 3:i + 7])[0]
                    for offset_occ, regs in ptr_registers.items():
                        if reg_base in regs:
                            member_accesses[offset_occ].add(disp)
                            member_accesses[offset_occ].add(disp + 8)
            i += 1

        return member_accesses

    def _find_offsets_via_assembly(self, pm, base, size):
        lea_addr = self._find_log_string_reference(pm, base, size)
        if not lea_addr:
            return None

        scan_start, func_bytes = self._read_function_body(pm, base, lea_addr)
        if not func_bytes:
            return None

        candidates = self._find_train_global_candidates(pm, scan_start, func_bytes)
        for train_instr_addr, global_addr, reg_train in candidates:
            start_idx = train_instr_addr - scan_start + 7

            ptr_registers = self._trace_pointer_loads(func_bytes, start_idx, reg_train)
            member_accesses = self._trace_double_accesses(func_bytes, start_idx, ptr_registers)

            for offset_occ, disps in member_accesses.items():
                for d in sorted(disps):
                    if (d + 8) in disps and d >= 0x1000:
                        if offset_occ == 0x18:
                            return global_addr, offset_occ, d

        return None

    def _find_via_fallback_string_reference(self, pm, base, size):
        lea_addr = self._find_log_string_reference(pm, base, size)
        if not lea_addr:
            return None

        scan_start, func_bytes = self._read_function_body(pm, base, lea_addr)
        if not func_bytes:
            return None

        candidates = self._find_train_global_candidates(pm, scan_start, func_bytes)
        if candidates:
            _, global_addr, _ = candidates[0]
            return global_addr, 0x18, 0x3430

        return None

    def _monitor_loop(self):
        while self._running:
            try:
                pm = pymem.Pymem(PROCESS_NAME)
                self.is_connected = True
                self.error_message = ""
                self.status_message = "Connected to MaSzyna. Resolving pointers..."

                module_base, module_size = self._get_module_info(pm, PROCESS_NAME)
                if module_base is None:
                    raise Exception(f"Could not find module '{PROCESS_NAME}'")

                result = self._find_offsets_via_assembly(pm, module_base, module_size)
                if result is None:
                    result = self._find_via_fallback_string_reference(pm, module_base, module_size)

                if result is None:
                    raise Exception("Failed to resolve pointer chain offsets")

                train_global_addr, mvOccupied_offset, V_offset = result
                self.status_message = "Connected and polling speed"

                while self._running:
                    try:
                        train_ptr = self._read_u64(pm, train_global_addr)
                        if train_ptr == 0:
                            self.current_speed_kmh = None
                            time.sleep(0.5)
                            continue

                        mvOccupied_ptr = self._read_u64(pm, train_ptr + mvOccupied_offset)
                        if mvOccupied_ptr == 0:
                            self.current_speed_kmh = None
                            time.sleep(0.5)
                            continue

                        v_address = mvOccupied_ptr + V_offset
                        velocity = self._read_double(pm, v_address)
                        self.current_speed_kmh = abs(velocity) * 3.6
                        time.sleep(0.05)

                    except pymem.exception.MemoryReadError:
                        self.current_speed_kmh = None
                        self.is_connected = False
                        self.status_message = "Memory read error, reattaching..."
                        break
                    except Exception as e:
                        self.current_speed_kmh = None
                        self.error_message = str(e)
                        time.sleep(1.0)

            except pymem.exception.ProcessNotFound:
                self.is_connected = False
                self.current_speed_kmh = None
                self.status_message = "Waiting for simulator to start..."
                time.sleep(2.0)
            except Exception as e:
                self.is_connected = False
                self.current_speed_kmh = None
                self.error_message = str(e)
                self.status_message = f"Error: {str(e)}"
                time.sleep(2.0)
