from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("novetest")
except PackageNotFoundError:
    # Source checkout without installation; fallback for development.
    # The `+local` suffix is a PEP 440 local-version identifier that
    # clearly signals "uninstalled development state".
    __version__ = "0.0.0+local"
