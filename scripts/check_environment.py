"""Read-only environment report; never starts or connects to AutoCAD."""

import importlib.metadata
import json
import sys


def main():
    report = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "python_supported": sys.version_info >= (3, 11),
        "autocad_integration_verified": False,
    }
    for package in ("mcp", "pydantic", "pywin32"):
        try:
            report[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report[package] = None
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"AutoCAD.Application.26\CLSID") as key:
                report["autocad_2027_registered_clsid"] = winreg.QueryValueEx(key, "")[0]
        except OSError:
            report["autocad_2027_registered_clsid"] = None
    print(json.dumps(report, indent=2))
    if not report["python_supported"] or not report["mcp"] or not report["pydantic"]:
        return 1
    if sys.platform == "win32" and not report["pywin32"]:
        return 1
    if sys.platform == "win32" and not report["autocad_2027_registered_clsid"]:
        print(
            "WARNING: AutoCAD 2027 COM registration not found. "
            "Install/repair full AutoCAD before use.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
