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
POLL_MILLISECONDS = 3000


class SufyanPisoNetTimerService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = DISPLAY_NAME
    _svc_description_ = "Supervises the Sufyan PisoNetTimer client application."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.process_handle = None
        self.process_id = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self._log("Stop requested by Service Control Manager")
        self._stop_app()
        win32event.SetEvent(self.hWaitStop)
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)

    def SvcDoRun(self):
        self._log("Service entered running state")
        try:
            while win32event.WaitForSingleObject(self.hWaitStop, POLL_MILLISECONDS) != win32event.WAIT_OBJECT_0:
                try:
                    if not self._is_app_running():
                        self._log("Client application is not running; launching")
                        self._close_process_handle()
                        self._launch_app()
                except Exception as exc:
                    self._log(f"Supervisor cycle error: {type(exc).__name__}: {exc}")
                    self._close_process_handle()
        finally:
            self._stop_app()
            self._log("Service stopped cleanly")

    def _is_app_running(self):
        if self.process_handle is None:
            return False
        try:
            return win32process.GetExitCodeProcess(self.process_handle) == win32process.STILL_ACTIVE
        except Exception as exc:
            self._log(f"Unable to query client process: {type(exc).__name__}: {exc}")
            return False

    def _get_interactive_session(self):
        session_id = win32ts.WTSGetActiveConsoleSessionId()
        if session_id != 0xFFFFFFFF:
            try:
                state = win32ts.WTSQuerySessionInformation(None, session_id, win32ts.WTSConnectState)
                if state == win32ts.WTSActive:
                    return session_id
            except Exception:
                pass
        try:
            for session in win32ts.WTSEnumerateSessions(None, 1, 0):
                if session["State"] == win32ts.WTSActive:
                    return session["SessionId"]
        except Exception as exc:
            self._log(f"Session enumeration failed: {type(exc).__name__}: {exc}")
        return None

    def _launch_app(self):
        if self._is_app_running():
            return
        if not os.path.exists(APP_EXE):
            self._log(f"Client application EXE not found: {APP_EXE}")
            return

        token = None
        env = None
        try:
            session_id = self._get_interactive_session()
            if session_id is None:
                self._log("No active interactive Windows session; will retry")
                return
            token = win32ts.WTSQueryUserToken(session_id)
            env = win32profile.CreateEnvironmentBlock(token, False)
            startup = win32process.STARTUPINFO()
            startup.lpDesktop = r"winsta0\default"
            flags = win32process.CREATE_UNICODE_ENVIRONMENT | win32process.CREATE_NEW_PROCESS_GROUP
            info = win32process.CreateProcessAsUser(
                token, None, f'"{APP_EXE}"', None, None, False,
                flags, env, APP_DIR, startup
            )
            self.process_handle = info[0]
            self.process_id = info[2]
            self._log(f"Client application launched; PID={self.process_id}")
        except Exception as exc:
            self._log(f"Client launch failed: {type(exc).__name__}: {exc}")
        finally:
            if env is not None:
                try:
                    win32profile.DestroyEnvironmentBlock(env)
                except Exception:
                    pass
            if token is not None:
                try:
                    win32security.CloseHandle(token)
                except Exception:
                    pass

    def _close_process_handle(self):
        if self.process_handle is not None:
            try:
                win32security.CloseHandle(self.process_handle)
            except Exception:
                pass
        self.process_handle = None
        self.process_id = None

    def _stop_app(self):
        if self.process_handle is not None:
            try:
                if self._is_app_running():
                    win32process.TerminateProcess(self.process_handle, 0)
            except Exception as exc:
                self._log(f"Could not stop client process: {type(exc).__name__}: {exc}")
            self._close_process_handle()

    def _log(self, message):
        try:
            log_dir = os.path.join(APP_DIR, "logs")
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, "service.log"), "a", encoding="utf-8") as log:
                log.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + message + "\n")
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SufyanPisoNetTimerService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SufyanPisoNetTimerService)
