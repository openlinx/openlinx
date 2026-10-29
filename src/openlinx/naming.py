"""The product name and names made from it (design D11 of 010-add-workspace-and-cli-contract)."""

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
