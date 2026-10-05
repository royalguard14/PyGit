import os
import sys
import time
import servicemanager
import win32event
import win32process
import win32profile
import win32security
import win32service
import win32serviceutil
import win32ts

SERVICE_NAME = "SufyanPisoNetTimer"
DISPLAY_NAME = "Sufyan PisoNetTimer"
APP_DIR = r"C:\sufyan"
APP_EXE = os.path.join(APP_DIR, "SufyanPisoNetTimer.exe")


class SufyanPisoNetTimerService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = DISPLAY_NAME
    _svc_description_ = "Sufyan PisoNetTimer application supervisor."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.process_handle = None
        self.process_id = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self._stop_app()
        win32event.SetEvent(self.hWaitStop)
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)

    def SvcDoRun(self):
        self._log("Service started")
        self._launch_app()
        while True:
            result = win32event.WaitForSingleObject(self.hWaitStop, 5000)
            if result == win32event.WAIT_OBJECT_0:
                break
            if self.process_handle is None:
                self._launch_app()
            else:
                code = win32process.GetExitCodeProcess(self.process_handle)
                if code != win32process.STILL_ACTIVE:
                    self._log(f"Application exited with code {code}; restarting")
                    self.process_handle = None
                    self.process_id = None
                    time.sleep(2)
                    self._launch_app()
        self._log("Service stopped")

    def _launch_app(self):
        if not os.path.exists(APP_EXE):
            self._log("Application EXE not found: " + APP_EXE)
            return

        try:
            session_id = win32ts.WTSGetActiveConsoleSessionId()
            if session_id == 0xFFFFFFFF:
                self._log("No active console session")
                return

            token = win32ts.WTSQueryUserToken(session_id)
            primary = win32security.DuplicateTokenEx(
                token,
                0x02000000,
                None,
                win32security.SecurityIdentification,
                win32security.TokenPrimary
            )

            env = win32profile.CreateEnvironmentBlock(primary, False)
            startup = win32process.STARTUPINFO()
            startup.lpDesktop = "winsta0\\default"

            command = '"' + APP_EXE + '"'
            flags = win32process.CREATE_UNICODE_ENVIRONMENT | win32process.CREATE_NEW_PROCESS_GROUP

            proc_info = win32process.CreateProcessAsUser(
                primary,
                None,
                command,
                None,
                None,
                False,
                flags,
                env,
                APP_DIR,
                startup
            )

            self.process_handle = proc_info[0]
            self.process_id = proc_info[2]
            self._log(f"Application started; PID={self.process_id}")

            try:
                win32profile.DestroyEnvironmentBlock(env)
            except Exception:
                pass
            try:
                win32security.CloseHandle(token)
            except Exception:
                pass
            try:
                win32security.CloseHandle(primary)
            except Exception:
                pass
        except Exception as e:
            self._log(f"Application launch failed: {type(e).__name__}: {e}")

    def _stop_app(self):
        if self.process_handle is not None:
            try:
                win32process.TerminateProcess(self.process_handle, 0)
            except Exception:
                pass
            self.process_handle = None
            self.process_id = None

    def _log(self, message):
        try:
            os.makedirs(os.path.join(APP_DIR, "logs"), exist_ok=True)
            with open(os.path.join(APP_DIR, "logs", "service.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + message + "\n")
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SufyanPisoNetTimerService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SufyanPisoNetTimerService)
