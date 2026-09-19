import shlex


def build_command_preview_args(command: str):
    """Parse a user-entered command into a safe argv preview without shell execution.

    This is intentionally conservative: it tokenizes the command string using
    POSIX shell rules and returns the argument vector, which can be used to show
    the preview in the GUI without invoking a shell.
    """
    if not command or not command.strip():
        return []
    return shlex.split(command, posix=True)
