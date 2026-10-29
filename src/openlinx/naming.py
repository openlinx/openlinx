"""The product name and names made from it (design D11 of 010-add-workspace-and-cli-contract)."""

from pathlib import PurePath

# The command users type, and the name of the package, its files and the robots token.
COMMAND_NAME = "linx"
PACKAGE_NAME = "openlinx"
# The product in prose, in --version and in the User-Agent's product token.
PRODUCT_NAME = "OpenLinx"
DATA_DIR_NAME = f".{PACKAGE_NAME}"
SETTINGS_FILE_NAME = f"{PACKAGE_NAME}.toml"
# Selects robots.txt groups and prefixed robots directives unless --robots-user-agent is given.
DEFAULT_ROBOTS_TOKEN = PACKAGE_NAME
# As users see it: symbolic, so text that names it is the same on every OS.
GLOBAL_DATA_DIR = f"~/{DATA_DIR_NAME}"


def invoked_command(program: str) -> str:
    """The console script that `program`, a process's argv[0], names; COMMAND_NAME when it runs
    some other way, such as `python -m` (design D4 of 021-rename-to-openlinx)."""
    # Windows may start the script as OPENLINX.EXE, whatever case PATHEXT gives.
    name = PurePath(program).name.lower().removesuffix(".exe")
    return name if name in (COMMAND_NAME, PACKAGE_NAME) else COMMAND_NAME
