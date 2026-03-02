import os
import sys


APP_VENDOR = "MedTech"
APP_NAME = "Prosthesis Sizing App"


# ---------------- INSTALL AND DATA PATHS ---------------- #
def install_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def user_data_dir() -> str:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return os.path.join(local_app_data, APP_VENDOR, APP_NAME)

    return os.path.join(install_base_dir(), "user_data")


def user_config_dir() -> str:
    return os.path.join(user_data_dir(), "config")


def user_queue_dir() -> str:
    return os.path.join(user_data_dir(), "data")
