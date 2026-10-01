"""Website Blocker  ·  by zadwen

  WebsiteBlocker.exe            -> parent control panel (asks for the PIN)
  WebsiteBlocker.exe --daemon   -> silent background service (started by Windows)
"""
import sys


def main():
    if "--daemon" in sys.argv[1:]:
        from core.daemon import run
        run()
        return

    from core import winutil
    if winutil.IS_WINDOWS and not winutil.is_admin():
        winutil.relaunch_as_admin()
        return

    from ui.app import run_gui
    run_gui()


if __name__ == "__main__":
    main()
