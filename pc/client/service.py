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
            if win32event.WaitForSingleObject(self.hWaitStop, 5000) == win32event.WAIT_OBJECT_0:
                break

            if self.process_handle is None:
                self._launch_app()
                continue

            try:
                code = win32process.GetExitCodeProcess(self.process_handle)
            except Exception:
                code = 0

            if code != win32process.STILL_ACTIVE:
                self._log(f"Application exited with code {code}; restarting")
                self._close_process_handle()
                time.sleep(2)
                self._launch_app()

        self._log("Service stopped")

    def _get_interactive_session(self):
        # Prefer the active console session. During Windows boot/logon this
        # can temporarily be unavailable, so fall back to any active session.
        session_id = win32ts.WTSGetActiveConsoleSessionId()
        if session_id != 0xFFFFFFFF:
            try:
                state = win32ts.WTSQuerySessionInformation(
                    None,
                    session_id,
                    win32ts.WTSConnectState
                )
                if state == win32ts.WTSActive:
                    return session_id
            except Exception:
                pass

        try:
            sessions = win32ts.WTSEnumerateSessions(None, 1, 0)
            for session in sessions:
                sid = session["SessionId"]
                if session["State"] == win32ts.WTSActive:
                    return sid
        except Exception:
            pass

        return None

    def _launch_app(self):
        if self.process_handle is not None:
            try:
                if win32process.GetExitCodeProcess(self.process_handle) == win32process.STILL_ACTIVE:
                    return
            except Exception:
                pass
            self._close_process_handle()

        if not os.path.exists(APP_EXE):
            self._log("Application EXE not found: " + APP_EXE)
            return

        token = None
        env = None

        try:
            session_id = self._get_interactive_session()
            if session_id is None:
                self._log("No active interactive session; retrying")
                return

            try:
                token = win32ts.WTSQueryUserToken(session_id)
            except Exception as e:
                self._log(
                    f"WTSQueryUserToken failed for session {session_id}: "
                    f"{type(e).__name__}: {e}; retrying"
                )
                return

            env = win32profile.CreateEnvironmentBlock(token, False)

            startup = win32process.STARTUPINFO()
            startup.lpDesktop = r"winsta0\default"

            flags = (
                win32process.CREATE_UNICODE_ENVIRONMENT
                | win32process.CREATE_NEW_PROCESS_GROUP
            )

            info = win32process.CreateProcessAsUser(
                token,
                None,
                f'"{APP_EXE}"',
                None,
                None,
                False,
                flags,
                env,
                APP_DIR,
                startup,
            )

            self.process_handle = info[0]
            self.process_id = info[2]
            self._log(f"Application started; PID={self.process_id}")

        except Exception as e:
            self._log(f"Application launch failed: {type(e).__name__}: {e}")

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
                win32process.TerminateProcess(self.process_handle, 0)
            except Exception:
                pass
            self._close_process_handle()

    def _log(self, message):
        try:
            os.makedirs(os.path.join(APP_DIR, "logs"), exist_ok=True)
            with open(
                os.path.join(APP_DIR, "logs", "service.log"),
                "a",
                encoding="utf-8",
            ) as f:
                f.write(
                    time.strftime("[%Y-%m-%d %H:%M:%S] ")
                    + message
                    + "\n"
                )
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SufyanPisoNetTimerService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SufyanPisoNetTimerService)
