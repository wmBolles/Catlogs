def parse_process_snapshot(raw_output: str):
    """Parse ps output built from a fixed set of columns.

    The parser intentionally avoids multi-word columns such as "lstart" because
    those can contain spaces and shift the remaining columns. Using a stable,
    single-token elapsed field keeps the process list safe for zombie entries and
    live processes alike.
    """
    rows = []
    for line in (raw_output or "").splitlines():
        line = line.strip()
        if not line:
            continue

        fields = line.split(None, 9)
        if len(fields) < 10:
            continue

        pid, ppid, user, name, cpu, mem, state, tty, elapsed, command = fields
        try:
            pid_value = int(pid)
            ppid_value = int(ppid)
            cpu_value = float(cpu)
            mem_value = float(mem)
        except ValueError:
            continue

        rows.append({
            "pid": pid_value,
            "ppid": ppid_value,
            "user": user,
            "name": name,
            "cpu": str(cpu_value),
            "mem": str(mem_value),
            "state": state,
            "tty": tty if tty != "?" else "none",
            "started": elapsed,
            "command": command,
        })
    return rows
