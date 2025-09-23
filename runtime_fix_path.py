# Runtime hook: ensure DLL search path includes application root and duplicate libffi if required
import os, sys, ctypes, shutil

base = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(sys.executable))) if getattr(sys, 'frozen', False) else os.path.abspath(os.path.dirname(__file__))

# Add base to DLL search path (Python 3.8+ on Windows)
try:
    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(base)
except Exception:
    pass

# Provide ffi.dll alias if only libffi-7.dll exists
ffi_candidates = ['ffi.dll','libffi-7.dll','libffi-8.dll','libffi.dll']
existing = {name: os.path.exists(os.path.join(base, name)) for name in ffi_candidates}
if not existing.get('ffi.dll'):
    for src_name in ('libffi-7.dll','libffi-8.dll','libffi.dll'):
        src_path = os.path.join(base, src_name)
        if os.path.exists(src_path):
            try:
                shutil.copy2(src_path, os.path.join(base, 'ffi.dll'))
            except Exception:
                pass
            break
