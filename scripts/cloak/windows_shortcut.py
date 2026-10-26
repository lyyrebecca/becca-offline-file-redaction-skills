"""Native Unicode IShellLinkW, avoiding WScript.Shell's ANSI path conversions."""
import ctypes,uuid
from pathlib import Path

class GUID(ctypes.Structure):
    _fields_=[('data',ctypes.c_ubyte*16)]
    def __init__(self,value):super().__init__();self.data[:]=uuid.UUID(value).bytes_le

def create_shortcut(destination,target,arguments,working_directory,icon):
    ole=ctypes.OleDLL('ole32');HRESULT=ctypes.c_long
    ole.CoInitializeEx.argtypes=[ctypes.c_void_p,ctypes.c_ulong];ole.CoInitializeEx.restype=HRESULT
    ole.CoCreateInstance.argtypes=[ctypes.POINTER(GUID),ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)];ole.CoCreateInstance.restype=HRESULT
    def checked(result):
        if result<0:raise OSError('WINDOWS_SHORTCUT_FAILED')
    def call(pointer,index,argtypes,*args):
        address=ctypes.cast(pointer,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents[index]
        result=ctypes.WINFUNCTYPE(HRESULT,ctypes.c_void_p,*argtypes)(address)(pointer,*args)
        checked(result);return result
    checked(ole.CoInitializeEx(None,2));link=ctypes.c_void_p();persist=ctypes.c_void_p()
    try:
        checked(ole.CoCreateInstance(ctypes.byref(GUID('00021401-0000-0000-c000-000000000046')),None,1,ctypes.byref(GUID('000214f9-0000-0000-c000-000000000046')),ctypes.byref(link)))
        call(link,20,[ctypes.c_wchar_p],str(target))
        call(link,11,[ctypes.c_wchar_p],arguments)
        call(link,9,[ctypes.c_wchar_p],str(working_directory))
        call(link,17,[ctypes.c_wchar_p,ctypes.c_int],str(icon),0)
        call(link,0,[ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)],ctypes.byref(GUID('0000010b-0000-0000-c000-000000000046')),ctypes.byref(persist))
        call(persist,6,[ctypes.c_wchar_p,ctypes.c_int],str(destination),1)
        # Confirm the Unicode target value before reporting success.
        buffer=ctypes.create_unicode_buffer(32768)
        call(link,3,[ctypes.c_wchar_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong],buffer,len(buffer),None,0)
        if buffer.value!=str(target) or not Path(destination).is_file():raise OSError('WINDOWS_SHORTCUT_FAILED')
    finally:
        if persist.value:call(persist,2,[])
        if link.value:call(link,2,[])
        ole.CoUninitialize()
