#!/usr/bin/env python3
"""Seagate 8 TB media test. Version 0.91.

Run this script. It compiles seagate-media-test.c when it needs to, and it
refuses to start a second writer. The test writes 499,998,720-byte patterned
files, reads them back uncached, treats a write of 4.5 seconds or more as
slow, reads those files again at the end of the group, and prints a statistics
line every ten files.

How to run it
  python3 seagate-media-test.py plan
      How many more files fit if 30, 40, or 50 decimal GB stay free.
      Decimal GB is 1000^3. Free space is the Available column of df -k.
      Filling to the last byte is printed too, and it is too tight.

  python3 seagate-media-test.py plan --reserve-gb 40
      Same count, plus the reserve you name if it is not 30, 40, or 50.
      --first 15611 also prints the file number that count would end on.
      --no-names skips the directory scan and only prints the free-space counts.

  python3 seagate-media-test.py run --groups 9
      Nine more sets of 500. This is the "9 more sets of 500" request.
      The first file is one past the highest finished name. Finished names are
      "good area", "good but slow", "good twice but slow", "failed", and
      "failed second read". A short "untested area" file is not finished, is
      not deleted, and is not rewritten.

  python3 seagate-media-test.py run --groups 10 --per 500 --first 11111 --slow 4.5
      The same knobs as the earlier runs: how many sets, how many files in a
      set, where to start, and the slow-write line. The default set size is
      500 and the default slow line is 4.5 seconds.

  python3 seagate-media-test.py watch
      Follow the logs. Stopping watch does not stop the writer.

  python3 seagate-media-test.py status
      Writer pid, last normal line, warning count, and error count.

  python3 seagate-media-test.py classify
      Read the detail log of the run that is already going and fill
      seagate-normal.log and seagate-warnings.log. It does not start a writer.
      Serious lines are appended to the error log only when they are not
      already there.

  python3 seagate-media-test.py capture-live
      Copy the screen of the run that is already going, then keep appending.
      That run was started before this script existed, so its screen was in
      /tmp. /tmp is lost on reboot. This command keeps a copy in this folder.
      Do not start it a second time while its copier is already running.

  python3 seagate-media-test.py self-test
      Check the free-space arithmetic against the count made before this run.
      It does not touch the drive.

Logs for a run you start with this version
  seagate-normal.log    Everything that is fine. A slow write is fine.
                        Needing a second read is fine. Both stay here.
  seagate-warnings.log  A read or a second read of 4.000 seconds or more
                        that still matched. It is not a failure. A second
                        read that matches does not get a third read.
  seagate-errors.log    Anything more serious: a mismatch, a partial file
                        left in place, a rename failure, a non-zero bad
                        count, or any single-file read or write of 15.000
                        seconds or more. That 15 second case is the
                        USB-bridge failure.

Logs already being filled by the run that is in progress
  seagate-screen.log    Screen lines copied from that run.
  seagate-detail.log    One line per file from that run.
  seagate-errors.log    Serious lines from that run. It stays empty while
                        every file matches and no read or write hits 15 seconds.
  seagate-times.txt     Write times for a later run. The running test keeps
                        its own copy in /tmp.
  seagate-capture.log   Notes from the copier. This is not test output.

What the test does
  Each file is (500000000 / 4096) * 4096 = 499998720 bytes. The write and the
  read bypass the file cache, and the write is followed by a full sync. The
  fill byte is ((file_number * 17) % 255) + 1. Each 4096-byte page starts with
  a 5-byte header: the file number in two base-255 digits, then the 0-based
  page index in three base-255 digits, least-significant digit first. A digit
  d is stored as d+1. The other 4091 bytes are the fill. A zero fill cannot
  catch the 15 second failure, so the pattern is never zero.

  A write of 4.5 seconds or more makes that ten get read at once. A match is
  renamed "good but slow N". Any other match in that ten is "good area N".
  A mismatch is "failed N". After the group, only the "good but slow" names
  are read again. A match becomes "good twice but slow N".

Leave these alone
  One writer. This script will not start another while one is alive.
  Files 00001 through 00600 are solid 0xFF from an older program. A finished
  name is skipped. Do not delete those files. This program would write the
  patterned form only for a number that has no finished file.
  "untested area 11002" is short. Leave it. Do not delete it.
  Do not fill the volume to 0 bytes free.
  Do not turn Wi-Fi on. The working path is the USB Ethernet adapter.
  Do not run seagate-media-test-bin by hand while any copy is running.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "seagate-media-test.c")
BINARY = os.path.join(HERE, "seagate-media-test-bin")
SCREEN = os.path.join(HERE, "seagate-screen.log")
DETAIL = os.path.join(HERE, "seagate-detail.log")
NORMAL = os.path.join(HERE, "seagate-normal.log")
WARNINGS = os.path.join(HERE, "seagate-warnings.log")
ERRORS = os.path.join(HERE, "seagate-errors.log")
SLOW_READ = Decimal("4.000")
TIMES = os.path.join(HERE, "seagate-times.txt")
STATE = os.path.join(HERE, "seagate-capture.state")
PIDFILE = os.path.join(HERE, "seagate-capture.pid")
CAPLOG = os.path.join(HERE, "seagate-capture.log")

VOLUME = "/Volumes/2020 Seagate 8TB"
FILE_BYTES = 499998720
FILE_KB = FILE_BYTES // 1024  # 488280
STALL = Decimal("15.000")
LIVE_STDOUT = "/tmp/seagate-groups-15610.stdout"
LIVE_DETAIL = "/tmp/seagate-groups-15610.txt"
LIVE_PID = 68132

# Longest prefix first so "failed second read" is not read as "failed".
FINISHED_PREFIXES = (
    "failed second read ",
    "good twice but slow ",
    "good but slow ",
    "good area ",
    "failed ",
)


def reserve_kb(gb: float) -> float:
    """Decimal GB (1000^3 bytes) expressed in df -k's 1024-byte blocks."""
    return gb * (1000 ** 3) / 1024


def files_that_fit(available_kb: int, reserve_gb: float) -> int:
    leave = reserve_kb(reserve_gb)
    if available_kb <= leave:
        return 0
    return int((available_kb - leave) // FILE_KB)


def leftover_bytes(available_kb: int, count: int) -> int:
    return available_kb * 1024 - count * FILE_BYTES


def available_kb(volume: str) -> int:
    out = subprocess.check_output(["df", "-k", "-P", volume], text=True)
    line = out.strip().splitlines()[-1]
    parts = line.split()
    if len(parts) < 4:
        raise SystemExit(f"could not read df -k for {volume}: {line}")
    return int(parts[3])


def highest_finished_in(names) -> int | None:
    best = None
    for name in names:
        for prefix in FINISHED_PREFIXES:
            tail = name[len(prefix):] if name.startswith(prefix) else ""
            if tail.isdigit():
                number = int(tail)
                if best is None or number > best:
                    best = number
                break
    return best


def highest_finished(volume: str) -> int | None:
    best = None
    with os.scandir(volume) as entries:
        for entry in entries:
            found = highest_finished_in((entry.name,))
            if found is not None and (best is None or found > best):
                best = found
    return best


def historical_plan_ok() -> None:
    """The free-space count from before this run. available was 2,284,457,964 KB."""
    available = 2284457964
    if files_that_fit(available, 30) != 4618:
        raise SystemExit("30 GB count drifted")
    if files_that_fit(available, 40) != 4598:
        raise SystemExit("40 GB count drifted")
    if files_that_fit(available, 50) != 4578:
        raise SystemExit("50 GB count drifted")
    if files_that_fit(available, 0) != 4678:
        raise SystemExit("fill-to-last count drifted")
    if 11111 + files_that_fit(available, 40) - 1 != 15708:
        raise SystemExit("40 GB end file drifted")
    if 11111 + files_that_fit(available, 30) - 1 != 15728:
        raise SystemExit("30 GB end file drifted")
    if 11111 + files_that_fit(available, 50) - 1 != 15688:
        raise SystemExit("50 GB end file drifted")
    names = [
        "good area 11001",
        "untested area 11002",
        "good twice but slow 11110",
        "failed second read 01244",
        "good but slow 00625",
    ]
    if highest_finished_in(names) != 11110:
        raise SystemExit("finished-name scan drifted")
    samples = {
        "W 12892 total_s=10.279 MBps=48.6": set(),
        "SECOND 12326 read_s=8.180 MBps=61.1 OK": set(),
        "R 13350 read_s=3.999 MBps=125.0 good": set(),
        "R 13350 read_s=4.887 MBps=102.3 good-but-slow": set(),
        "BAD W 11002 partial left in place": {"bad"},
        "BAD R 00001 read_s=15.100 bad_bytes=4": {"bad", "stall"},
        "STALL W 00001 seconds=15.000 MBps=33.3 bytes matched": {"stall"},
        "W 00001 total_s=15.000 MBps=33.3": {"stall"},
        "W 00001 total_s=14.999 MBps=33.3": set(),
        "WRITE 00001-00010 min_s=4.000 median_s=4.000 mean_s=4.000 max_s=15.000 MBps=33.3 elapsed_s=40 bad=0": {"stall"},
        "WRITE 00001-00010 min_s=4.000 median_s=4.000 mean_s=4.000 max_s=4.500 MBps=100.0 elapsed_s=40 bad=1": {"bad"},
        "GROUP 1/9 DONE elapsed_s=10 write_bad=0 read_bad=0 second_bad=0": set(),
        "GROUP 10/10 DONE elapsed_s=10 write_bad=1 read_bad=0 second_bad=0": {"bad"},
        "ALL DONE files=4500 elapsed_s=10 bad=0": set(),
        "ALL DONE files=5000 elapsed_s=10 bad=1": {"bad"},
        "READ 13341-13350 min_s=4.400 median_s=4.437 mean_s=4.512 max_s=4.887 MBps=110.8 elapsed_s=2330 bad=0": set(),
        "READ 00001-00010 min_s=3.100 median_s=3.200 mean_s=3.200 max_s=3.999 MBps=150.0 elapsed_s=32 bad=0": set(),
    }
    classes = {
        "W 12892 total_s=10.279 MBps=48.6": "normal",
        "SECOND 12326 read_s=8.180 MBps=61.1 OK": "warning",
        "R 13350 read_s=3.999 MBps=125.0 good": "normal",
        "R 13350 read_s=4.000 MBps=125.0 good": "warning",
        "R 13350 read_s=4.887 MBps=102.3 good-but-slow": "warning",
        "BAD W 11002 partial left in place": "error",
        "W 00001 total_s=15.000 MBps=33.3": "error",
        "READ 13341-13350 min_s=4.400 median_s=4.437 mean_s=4.512 max_s=4.887 MBps=110.8 elapsed_s=2330 bad=0": "warning",
        "READ 00001-00010 min_s=3.100 median_s=3.200 mean_s=3.200 max_s=3.999 MBps=150.0 elapsed_s=32 bad=0": "normal",
        "WRITE 00001-00010 min_s=4.500 median_s=4.600 mean_s=4.600 max_s=5.000 MBps=100.0 elapsed_s=50 bad=0": "normal",
        "ALL DONE files=4500 elapsed_s=10 bad=0": "normal",
    }
    for line, expect in samples.items():
        got = error_kinds(line)
        if got != expect:
            raise SystemExit(f"error class drifted for {line!r}: {got} != {expect}")
    for line, expect in classes.items():
        got = log_class(line)
        if got != expect:
            raise SystemExit(f"log class drifted for {line!r}: {got} != {expect}")


def processes():
    out = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_s, cmd = line.split(None, 1)
        rows.append((int(pid_s), cmd))
    return rows


def is_writer_cmd(cmd: str) -> bool:
    if not cmd or "seagate-media-test.py" in cmd:
        return False
    argv0 = cmd.split()[0]
    base = os.path.basename(argv0)
    if base in {"caffeinate", "tail", "python3", "python", "bash", "sh", "cc"}:
        return False
    return base.startswith("seagate-groups") or base == "seagate-media-test-bin"


def find_writers():
    return [(pid, cmd) for pid, cmd in processes() if is_writer_cmd(cmd)]


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def follower_pid() -> int | None:
    try:
        with open(PIDFILE) as handle:
            pid = int(handle.read().strip())
    except (OSError, ValueError):
        return None
    if pid_alive(pid):
        return pid
    return None


def ensure_binary() -> str:
    if not os.path.isfile(SOURCE):
        raise SystemExit(f"missing source {SOURCE}")
    src_time = os.path.getmtime(SOURCE)
    if not os.path.isfile(BINARY) or os.path.getmtime(BINARY) < src_time:
        subprocess.check_call(
            ["cc", "-O2", "-Wall", "-Wextra", "-o", BINARY, SOURCE],
            cwd=HERE,
        )
    return BINARY


def _decimal_field(line: str, key: str) -> Decimal | None:
    at = line.find(key)
    if at < 0:
        return None
    token = line[at + len(key):].split()[0]
    try:
        return Decimal(token)
    except Exception:
        return None


def error_kinds(line: str) -> set[str]:
    """bad: a real failure. stall: one I/O printed at 15.000 s or more.

    A slow file that only needs a second read is neither.
    """
    text = line.strip()
    kinds: set[str] = set()
    if not text or text.startswith("#"):
        return kinds
    if text.startswith("BAD "):
        kinds.add("bad")
    if text.startswith("STALL "):
        kinds.add("stall")
    for key in ("total_s=", "read_s=", "max_s=", "seconds="):
        value = _decimal_field(text, key)
        if value is not None and value >= STALL:
            kinds.add("stall")
    bad_at = text.find(" bad=")
    if bad_at >= 0:
        token = text[bad_at + len(" bad="):].split()[0]
        if token.isdigit() and int(token) != 0:
            kinds.add("bad")
    if text.startswith("GROUP ") and " DONE " in text:
        counts = []
        for key in ("write_bad=", "read_bad=", "second_bad="):
            value = _decimal_field(text, key)
            counts.append(value)
        if all(v is not None for v in counts) and any(v != 0 for v in counts):
            kinds.add("bad")
    return kinds


def is_slow_read(line: str) -> bool:
    """A matching read at 4.000 seconds or more, and under the 15 second stall."""
    text = line.strip()
    if not text or text.startswith("#") or error_kinds(text):
        return False
    parts = text.split()
    if len(parts) < 2:
        return False
    per_file = parts[0] == "R" or (parts[0] == "SECOND" and "-" not in parts[1])
    batch = parts[0] in {"READ", "SECOND"} and "-" in parts[1]
    key = "read_s=" if per_file else "max_s=" if batch else ""
    if not key:
        return False
    value = _decimal_field(text, key)
    return value is not None and SLOW_READ <= value < STALL


def log_class(line: str) -> str:
    if error_kinds(line):
        return "error"
    if is_slow_read(line):
        return "warning"
    return "normal"


def append_text(path: str, text: str) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()


def read_exact(path: str) -> tuple[bytes, int]:
    """Read a stable prefix that ends on a line.

    The writer only appends. Stopping at the last newline leaves the
    unfinished tail for the copier, so a line is never split across the
    first copy and the follower.
    """
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(0)
        blob = handle.read(size)
    if blob.endswith(b"\n") or not blob:
        return blob, len(blob)
    cut = blob.rfind(b"\n")
    if cut < 0:
        return b"", 0
    return blob[:cut + 1], cut + 1


def last_physical_line(blob: bytes) -> str:
    text = blob.decode("utf-8", "replace").strip()
    if not text:
        return "(empty)"
    return text.splitlines()[-1]


def scan_errors(blob: bytes) -> tuple[int, int, list[str]]:
    bad_n = 0
    stall_n = 0
    lines = []
    for line in blob.decode("utf-8", "replace").splitlines():
        kinds = error_kinds(line)
        if not kinds:
            continue
        if "bad" in kinds:
            bad_n += 1
        if "stall" in kinds:
            stall_n += 1
        lines.append(line)
    return bad_n, stall_n, lines


def load_state() -> dict:
    with open(STATE, encoding="utf-8") as handle:
        return json.load(handle)


def save_state(state: dict) -> None:
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, STATE)


def cmd_plan(args) -> int:
    historical_plan_ok()
    free = available_kb(args.volume)
    tb = free * 1024 / 1e12
    print(f"Free space on {args.volume}: {free:,} KB (df -k Available), {tb:.3f} TB.")
    print(f"Each file is {FILE_BYTES:,} bytes ({FILE_KB:,} KB).")
    print("A reserve is decimal GB (1000^3 bytes), converted to 1024-byte blocks.")
    print("Files that fit = floor((available KB - reserve KB) / 488280).")
    print()
    reserves = [30, 40, 50]
    if args.reserve_gb not in reserves:
        reserves.append(args.reserve_gb)
    for gb in reserves:
        count = files_that_fit(free, gb)
        line = f"{gb:g} decimal GB left free: {count:,} more files."
        if args.first is not None and count:
            last = args.first + count - 1
            line += f" From file {args.first}, that ends at file {last}."
        print(line)
    fill = files_that_fit(free, 0)
    left = leftover_bytes(free, fill)
    print()
    print(f"Filling to the last byte would be {fill:,} more files and would leave {left:,} bytes.")
    print("That is too tight. Leave at least 30 GB free.")
    if args.no_names:
        print("Name scan skipped.")
        return 0
    print()
    finished = highest_finished(args.volume)
    if finished is None:
        print("No finished test name was found. A later run would start at file 1.")
    else:
        print(f"Highest finished file is {finished}.")
        print(f"A later run, after the current writer has exited, would start at file {finished + 1}.")
    print("An \"untested area\" name is not finished. File 11002 stays where it is.")
    writers = find_writers()
    if writers:
        pid, cmd = writers[0]
        print(f"A writer is already running (pid {pid}: {cmd}). plan does not start or stop it.")
    return 0


def cmd_run(args) -> int:
    writers = find_writers()
    if writers:
        pid, cmd = writers[0]
        print(f"A writer is already running (pid {pid}: {cmd}).")
        print("This script will not start a second writer.")
        return 1
    follower = follower_pid()
    if follower is not None:
        print(f"The log copier is still following the current run (pid {follower}).")
        print("Wait until that copier exits, then run this again.")
        return 1
    if args.per < 10 or args.per % 10 != 0:
        print("The set size has to be a multiple of 10.")
        return 2
    if args.groups < 1 or args.slow <= 0:
        print("Groups and the slow line have to be positive.")
        return 2
    if args.first is None:
        finished = highest_finished(args.volume)
        first = 1 if finished is None else finished + 1
    else:
        first = args.first
    if first < 1:
        print("The first file number has to be 1 or more.")
        return 2
    last = first + args.groups * args.per - 1
    maxf = max(20000, last + 1)
    binary = ensure_binary()
    command = [
        "caffeinate", "-i", binary,
        args.volume, str(first), str(args.groups), str(args.per),
        f"{args.slow:.1f}", NORMAL, TIMES, WARNINGS, ERRORS, str(maxf),
    ]
    print("Command:")
    print(" ".join(command))
    print(f"Normal log: {NORMAL}")
    print(f"Warnings log: {WARNINGS}")
    print(f"Error log: {ERRORS}")
    print(f"Files {first} through {last}.")
    if args.dry_run:
        print("Dry run. No writer was started.")
        return 0
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(NORMAL, "a", encoding="utf-8") as normal:
        normal.write(
            f"# run {stamp} first={first} groups={args.groups} per={args.per} "
            f"slow={args.slow:.1f} maxf={maxf}\n"
        )
        normal.flush()
    proc = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=HERE,
    )
    print(f"Started writer pid {proc.pid}. Stopping this script does not stop it.")
    return 0


def cmd_watch(_args) -> int:
    files = [path for path in (SCREEN, NORMAL, WARNINGS, ERRORS) if os.path.isfile(path)]
    if not files:
        print(f"No logs yet in {HERE}")
        return 1
    os.execvp("tail", ["tail", "-n", "20", "-F", *files])
    return 1


def cmd_status(_args) -> int:
    writers = find_writers()
    if writers:
        for pid, cmd in writers:
            print(f"Writer pid {pid}: {cmd}")
    else:
        print("No writer is running.")
    follower = follower_pid()
    if follower is not None:
        print(f"Log copier pid {follower}.")
    else:
        print("No log copier is running.")
    last = ""
    for path, label in ((NORMAL, "normal"), (SCREEN, "screen")):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip() and not line.startswith("#"):
                    last = line.rstrip("\n")
        if last:
            print(f"Last {label} line: {last}")
            break
    if not last:
        print(f"No normal or screen log in {HERE}")
    for path, label in ((WARNINGS, "Warning"), (ERRORS, "Error")):
        notes = 0
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.strip() and not line.startswith("#"):
                        notes += 1
            print(f"{label} lines: {notes} in {path}")
        else:
            print(f"No {label.lower()} log at {path}")
    return 0


def cmd_classify(args) -> int:
    """Split an existing detail log. Does not start a writer or touch the volume."""
    if not os.path.isfile(args.detail):
        print(f"No detail log at {args.detail}")
        return 1
    normal_lines = []
    warn_lines = []
    err_lines = []
    with open(args.detail, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            kind = log_class(line)
            if kind == "error":
                err_lines.append(line)
            elif kind == "warning":
                warn_lines.append(line)
            else:
                normal_lines.append(line)
    with open(NORMAL, "w", encoding="utf-8") as handle:
        handle.write("# Normal log. Fine results only. A slow write is normal.\n")
        handle.write(f"# Built by classify from {args.detail}\n")
        for line in normal_lines:
            handle.write(line + "\n")
    with open(WARNINGS, "w", encoding="utf-8") as handle:
        handle.write("# Warnings. A read of 4.000 seconds or more that still matched.\n")
        handle.write("# A matching second read is not a failure and does not get a third read.\n")
        handle.write(f"# Built by classify from {args.detail}\n")
        for line in warn_lines:
            handle.write(line + "\n")
    already = set()
    if os.path.isfile(ERRORS):
        with open(ERRORS, encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                already.add(raw.rstrip("\n"))
    added = 0
    with open(ERRORS, "a", encoding="utf-8") as handle:
        if not already:
            handle.write("# Error log. Mismatches, partial files, rename failures, and 15.000 second stalls.\n")
        for line in err_lines:
            if line not in already:
                handle.write(line + "\n")
                added += 1
    print(f"Normal lines: {len(normal_lines)} in {NORMAL}")
    print(f"Warning lines: {len(warn_lines)} in {WARNINGS}")
    print(f"Serious lines already recorded or added: {len(err_lines)} found, {added} appended to {ERRORS}")
    print("No writer was started.")
    return 0


def screen_header(pid: int, source: str) -> str:
    return (
        "# Screen log for the Seagate media test.\n"
        "# Everything that has gone to the screen is here, including the run\n"
        "# that was already going when this file was created.\n"
        f"# Source at capture: {source}\n"
        f"# Writer pid at capture: {pid}\n"
        "# New lines are appended. Comment lines start with #.\n"
    )


def detail_header(pid: int, source: str) -> str:
    return (
        "# Per-file log for the Seagate media test.\n"
        "# One line per file, plus the same summary lines that went to the screen.\n"
        "# This is the file to analyze later. The screen log does not name every time.\n"
        f"# Source at capture: {source}\n"
        f"# Writer pid at capture: {pid}\n"
    )


def error_header(bad_n: int, stall_n: int, nbytes: int, last_line: str) -> str:
    return (
        "# Error log for the Seagate media test.\n"
        "# A file that is only slow, and only needs a second read, is not an error.\n"
        "# Recorded here: a mismatch, a partial file left in place, a rename failure,\n"
        "# a batch or group line with a non-zero bad count, and any single-file I/O\n"
        "# of 15.000 seconds or more. That 15 second case is the USB-bridge stall.\n"
        "# A second read that matches does not get a third read and is not listed.\n"
        f"# Scan of {nbytes} detail-log bytes: bad_lines={bad_n} stall_lines={stall_n}.\n"
        f"# Last scanned detail line: {last_line}\n"
    )


def cmd_capture_live(args) -> int:
    follower = follower_pid()
    if follower is not None:
        print(f"Log copier pid {follower} is already running. The logs were not rewritten.")
        return 0
    if os.path.isfile(STATE) and os.path.isfile(SCREEN) and os.path.isfile(DETAIL):
        print("Resuming the copier from the saved offsets. Existing logs were kept.")
        return spawn_follower()
    if not os.path.isfile(args.stdout) or not os.path.isfile(args.detail):
        print("The live /tmp logs are not there, and this folder has no capture to resume.")
        return 1
    screen_blob, screen_n = read_exact(args.stdout)
    detail_blob, detail_n = read_exact(args.detail)
    bad_n, stall_n, error_lines = scan_errors(detail_blob)
    with open(SCREEN, "wb") as handle:
        handle.write(screen_header(args.pid, args.stdout).encode())
        handle.write(screen_blob)
    with open(DETAIL, "wb") as handle:
        handle.write(detail_header(args.pid, args.detail).encode())
        handle.write(detail_blob)
    with open(ERRORS, "w", encoding="utf-8") as handle:
        handle.write(error_header(bad_n, stall_n, detail_n, last_physical_line(detail_blob)))
        for line in error_lines:
            handle.write(line + "\n")
    save_state({
        "stdout_path": args.stdout,
        "detail_path": args.detail,
        "stdout_offset": screen_n,
        "detail_offset": detail_n,
        "writer_pid": args.pid,
        "screen_log": SCREEN,
        "detail_log": DETAIL,
        "error_log": ERRORS,
    })
    print(f"Copied {screen_n:,} screen bytes to {SCREEN}")
    print(f"Copied {detail_n:,} detail bytes to {DETAIL}")
    print(f"Error scan: bad_lines={bad_n} stall_lines={stall_n}")
    print(f"Error log: {ERRORS}")
    return spawn_follower()


def spawn_follower() -> int:
    log = open(CAPLOG, "a", encoding="utf-8")
    log.write(f"# capture spawn {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    log.flush()
    proc = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "_follow"],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        cwd=HERE,
    )
    with open(PIDFILE, "w", encoding="utf-8") as handle:
        handle.write(str(proc.pid) + "\n")
    print(f"Log copier pid {proc.pid}. It appends new screen lines in this folder.")
    print("The writer was not restarted.")
    return 0


def take_lines(pending: str, data: bytes) -> tuple[list[str], str]:
    text = pending + data.decode("utf-8", "replace")
    if "\n" not in text:
        return [], text
    parts = text.split("\n")
    return parts[:-1], parts[-1]


def read_from(path: str, offset: int) -> tuple[bytes, int]:
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        end = handle.tell()
        if end < offset:
            return b"", offset
        handle.seek(offset)
        data = handle.read(end - offset)
    return data, offset + len(data)


def cmd_follow() -> int:
    with open(PIDFILE, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()) + "\n")
    state = load_state()
    pending = {"stdout": "", "detail": ""}
    idle = 0
    print(f"following writer {state['writer_pid']} from stdout {state['stdout_offset']} detail {state['detail_offset']}", flush=True)
    try:
        while True:
            grew = False
            chunks = []
            for key, source, dest in (
                ("stdout", state["stdout_path"], state["screen_log"]),
                ("detail", state["detail_path"], state["detail_log"]),
            ):
                if not os.path.isfile(source):
                    chunks.append((key, b"", state[f"{key}_offset"]))
                    continue
                data, new_off = read_from(source, state[f"{key}_offset"])
                if data:
                    grew = True
                    with open(dest, "ab") as handle:
                        handle.write(data)
                        handle.flush()
                chunks.append((key, data, new_off))
            for key, data, new_off in chunks:
                if key == "detail" and data:
                    lines, pending["detail"] = take_lines(pending["detail"], data)
                    with open(state["error_log"], "a", encoding="utf-8") as handle:
                        for line in lines:
                            if error_kinds(line):
                                handle.write(line + "\n")
                        handle.flush()
                elif key == "stdout" and data:
                    _lines, pending["stdout"] = take_lines(pending["stdout"], data)
                off_key = "stdout_offset" if key == "stdout" else "detail_offset"
                state[off_key] = new_off
            save_state(state)
            if grew:
                idle = 0
                time.sleep(0.5)
                continue
            if pid_alive(int(state["writer_pid"])):
                idle = 0
                time.sleep(1)
                continue
            idle += 1
            if idle >= 3:
                append_text(
                    state["screen_log"],
                    f"# follow stopped. writer pid {state['writer_pid']} is gone and both logs were idle.\n",
                )
                print("follow stopped", flush=True)
                break
            time.sleep(1)
    finally:
        try:
            with open(PIDFILE, encoding="utf-8") as handle:
                recorded = int(handle.read().strip())
            if recorded == os.getpid():
                os.remove(PIDFILE)
        except (OSError, ValueError):
            pass
    return 0


def cmd_self_test(_args) -> int:
    historical_plan_ok()
    print("self-test passed")
    print("30 GB -> 4618 files, through 15728 if started at 11111")
    print("40 GB -> 4598 files, through 15708 if started at 11111")
    print("50 GB -> 4578 files, through 15688 if started at 11111")
    print("Fill to the last byte -> 4678 files, and that is too tight")
    print("File 11002 is not a finished name. File 11110 is.")
    print("A 10.279 s write is normal. An 8.180 s second read is a warning.")
    print("A read under 4.000 s is normal. A matching read of 4.000 s or more is a warning.")
    print("A partial, a mismatch, a non-zero bad count, and a 15.000 s I/O are errors.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seagate-media-test.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="How many more files fit at a 30, 40, or 50 GB reserve")
    plan.add_argument("--volume", default=VOLUME)
    plan.add_argument("--reserve-gb", type=float, default=40)
    plan.add_argument("--first", type=int, default=None, help="Print the end file if a run started here")
    plan.add_argument("--no-names", action="store_true", help="Skip the directory scan")
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run", help="Write and read N more sets. Refuses if a writer is running")
    run.add_argument("--groups", type=int, required=True, help="How many sets. 9 was the latest request")
    run.add_argument("--per", type=int, default=500, help="Files in a set. Default 500")
    run.add_argument("--first", type=int, default=None, help="First file. Default is one past the highest finished name")
    run.add_argument("--slow", type=float, default=4.5, help="Slow-write line in seconds. Default 4.5")
    run.add_argument("--volume", default=VOLUME)
    run.add_argument("--dry-run", action="store_true", help="Print the command and do not start a writer")
    run.set_defaults(func=cmd_run)

    watch = sub.add_parser("watch", help="Follow the screen log in this folder")
    watch.set_defaults(func=cmd_watch)

    status = sub.add_parser("status", help="Writer, last screen line, and error-log count")
    status.set_defaults(func=cmd_status)

    cap = sub.add_parser("capture-live", help="Copy the running test's screen into this folder and keep following it")
    cap.add_argument("--stdout", default=LIVE_STDOUT)
    cap.add_argument("--detail", default=LIVE_DETAIL)
    cap.add_argument("--pid", type=int, default=LIVE_PID)
    cap.set_defaults(func=cmd_capture_live)

    test = sub.add_parser("self-test", help="Check the reserve arithmetic. Does not touch the drive")
    test.set_defaults(func=cmd_self_test)

    classify = sub.add_parser("classify", help="Split a detail log into normal, warnings, and errors. Does not start a writer")
    classify.add_argument("--detail", default=DETAIL)
    classify.set_defaults(func=cmd_classify)
    return parser


def main(argv: list[str]) -> int:
    if argv[:1] == ["_follow"]:
        return cmd_follow()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
