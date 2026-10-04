"""The product name and names made from it (design D11 of 010-add-workspace-and-cli-contract)."""

# A working name until the product name is chosen; a rename edits this module only.
APP_NAME = "spider"
DATA_DIR_NAME = f".{APP_NAME}"
SETTINGS_FILE_NAME = f"{APP_NAME}.toml"
# As users see it: symbolic, so text that names it is the same on every OS.
GLOBAL_DATA_DIR = f"~/{DATA_DIR_NAME}"
