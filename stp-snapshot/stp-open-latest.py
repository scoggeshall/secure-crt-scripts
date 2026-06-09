# $language = "python"
# $interface = "1.0"

# Open the newest local STP snapshot folder.
# If stp-diff.txt exists in that folder, open the diff file instead.

import os


SCRIPT_TITLE = "Open Latest STP Snapshot"
OUTPUT_ROOT = r"C:\scripts\secure-crt\outputs\stp-snapshot"
DIFF_FILE_NAME = "stp-diff.txt"


def Main():
    if not os.path.isdir(OUTPUT_ROOT):
        crt.Dialog.MessageBox(
            "STP snapshot output folder not found:\n\n" + OUTPUT_ROOT,
            SCRIPT_TITLE
        )
        return

    latest_folder = find_latest_folder(OUTPUT_ROOT)
    if latest_folder == "":
        crt.Dialog.MessageBox(
            "No snapshot folders were found under:\n\n" + OUTPUT_ROOT,
            SCRIPT_TITLE
        )
        return

    diff_path = os.path.join(latest_folder, DIFF_FILE_NAME)
    if os.path.exists(diff_path):
        target = diff_path
    else:
        target = latest_folder

    try:
        os.startfile(target)
    except Exception as exc:
        crt.Dialog.MessageBox(
            "Could not open:\n\n" + target + "\n\n" + str(exc),
            SCRIPT_TITLE
        )


def find_latest_folder(root):
    latest_folder = ""
    latest_time = None

    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue

        try:
            modified_time = os.path.getmtime(path)
        except Exception:
            continue

        if latest_time is None:
            latest_time = modified_time
            latest_folder = path
            continue

        if modified_time > latest_time:
            latest_time = modified_time
            latest_folder = path
            continue

        if modified_time == latest_time and path > latest_folder:
            latest_folder = path

    return latest_folder


Main()
