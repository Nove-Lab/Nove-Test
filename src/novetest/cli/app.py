from cyclopts import App

from novetest import __version__

app = App(name="novetest", version=__version__)


def main() -> None:
    app()
