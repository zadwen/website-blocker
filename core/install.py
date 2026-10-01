"""Install / repair / remove the hidden background service (a SYSTEM startup task)."""
import base64
import codecs
import os
import shutil
import subprocess
import sys
import tempfile
import time
from xml.sax.saxutils import escape

from . import config, doh, hosts
from .daemon import MUTEX_NAME
from .winutil import CREATE_NO_WINDOW, DETACHED_PROCESS, IS_WINDOWS, run_hidden

TASK_NAME = "WebsiteBlockerService"
EXE_NAME = "WebsiteBlocker.exe"
INSTALL_DIR = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "WebsiteBlocker")

_TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/Task">
  <RegistrationInfo><Description>Website Blocker background service</Description></RegistrationInfo>
  <Triggers>
    <BootTrigger><Enabled>true</Enabled></BootTrigger>
    <TimeTrigger>
      <Repetition><Interval>PT5M</Interval></Repetition>
      <StartBoundary>2024-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Hidden>true</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def installed_exe():
    return os.path.join(INSTALL_DIR, EXE_NAME)


def _service_command():
    """(command, arguments) the task should run."""
    if getattr(sys, "frozen", False):
        return installed_exe(), "--daemon"
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    main_py = os.path.abspath(sys.argv[0])
    return (pyw if os.path.exists(pyw) else py), '"%s" --daemon' % main_py


def _schtasks(*args):
    return run_hidden(["schtasks", *args])


def is_installed():
    return IS_WINDOWS and _schtasks("/query", "/tn", TASK_NAME).returncode == 0


def daemon_running():
    if not IS_WINDOWS:
        return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenMutexW.restype = ctypes.c_void_p
    k32.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k32.OpenMutexW(0x00100000, False, MUTEX_NAME)  # SYNCHRONIZE
    if h:
        k32.CloseHandle(h)
        return True
    return False


def _copy_exe():
    """Copy the running .exe into Program Files (admin-only writable)."""
    os.makedirs(INSTALL_DIR, exist_ok=True)
    src, dst = os.path.abspath(sys.executable), installed_exe()
    if os.path.normcase(src) == os.path.normcase(dst):
        return
    last = None
    for _ in range(20):
        try:
            shutil.copy2(src, dst)
            return
        except PermissionError as e:
            last = e
            time.sleep(0.5)
    raise last


def _create_task_powershell(command, arguments):
    q = lambda t: t.replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
$action = New-ScheduledTaskAction -Execute '{q(command)}' -Argument '{q(arguments)}'
$boot = New-ScheduledTaskTrigger -AtStartup
$again = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 9000)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger @($boot, $again) -Principal $principal -Settings $settings -Force | Out-Null
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    res = run_hidden(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                      "-EncodedCommand", encoded])
    if res.returncode != 0:
        raise RuntimeError("PowerShell: " + (res.stderr or res.stdout).strip())


def _create_task_xml(command, arguments):
    xml = _TASK_XML.format(command=escape(command), arguments=escape(arguments))
    fd, tmp = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    try:
        with open(tmp, "wb") as f:
            f.write(codecs.BOM_UTF16_LE + xml.replace("\n", "\r\n").encode("utf-16-le"))
        res = _schtasks("/create", "/tn", TASK_NAME, "/xml", tmp, "/f")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if res.returncode != 0:
        raise RuntimeError("schtasks: " + (res.stderr or res.stdout).strip())


def install():
    """Install or repair. Needs administrator rights."""
    if not IS_WINDOWS:
        raise RuntimeError("The background service only works on Windows.")
    config.ensure_data_dir()
    config.lock_down(config.data_dir())

    _schtasks("/end", "/tn", TASK_NAME)  # ignore errors (may not exist yet)
    if getattr(sys, "frozen", False):
        _copy_exe()
    command, arguments = _service_command()

    errors = []
    for creator in (_create_task_powershell, _create_task_xml):
        try:
            creator(command, arguments)
            break
        except Exception as e:
            errors.append(str(e))
    else:
        raise RuntimeError("Could not create the startup task:\n\n" + "\n\n".join(errors))
    _schtasks("/run", "/tn", TASK_NAME)


def uninstall():
    """Remove the service, every block, browser policies and all files."""
    if not IS_WINDOWS:
        raise RuntimeError("Windows only.")
    _schtasks("/end", "/tn", TASK_NAME)
    _schtasks("/delete", "/tn", TASK_NAME, "/f")
    time.sleep(1)
    hosts.apply([])
    try:
        doh.apply(False)
    except Exception:
        pass
    cmd = 'ping -n 4 127.0.0.1 >nul & rmdir /s /q "%s" & rmdir /s /q "%s"' % (
        INSTALL_DIR, config.data_dir())
    subprocess.Popen(["cmd", "/c", cmd], creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                     close_fds=True)