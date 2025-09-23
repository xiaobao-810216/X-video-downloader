import sys, os, glob
print('base_prefix =', sys.base_prefix)
dll_dir = os.path.join(sys.base_prefix, 'DLLs')
print('dll_dir =', dll_dir, 'exists=', os.path.isdir(dll_dir))
print('ffi dlls =', [os.path.basename(p) for p in glob.glob(os.path.join(dll_dir, '*ffi*.dll'))])
print('_ctypes.pyd exists =', os.path.exists(os.path.join(dll_dir, '_ctypes.pyd')))
