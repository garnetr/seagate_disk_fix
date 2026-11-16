# Seagate disk fix

Version 0.90.

This folder is the Seagate 8 TB media test: the program, the run notes, and the logs copied off the screen.

Run `python3 seagate-media-test.py --help` for the full how-to. The commands are:

- `python3 seagate-media-test.py plan` shows how many more 499,998,720-byte files fit if 30, 40, or 50 decimal GB stay free.
- `python3 seagate-media-test.py run --groups 9` writes and reads nine more sets of 500. It skips finished names and will not start a second writer.
- `python3 seagate-media-test.py watch` follows `seagate-screen.log`.
- `python3 seagate-media-test.py status` shows the writer, the last screen line, and the error count.

`seagate-media-test.c` is the test. The Python script compiles it to `seagate-media-test-bin` when the source is newer. Run the Python script.

Logs in this folder:

- `seagate-screen.log` is everything that went to the screen.
- `seagate-detail.log` is one line per file, for a later look at each time.
- `seagate-errors.log` is mismatches, partial files left in place, rename failures, and any single-file read or write of 15.000 seconds or more. A file that is only slow, and only needs a second read, is not an error.

`SEAGATE-8TB-HANDOFF.md` is the resume note for the drive and the runs so far.

One writer at a time. Do not delete a short `untested area` file. Do not fill the volume to 0 bytes free.
