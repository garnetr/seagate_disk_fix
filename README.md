# Seagate disk fix

Version 0.91.

This folder is the Seagate 8 TB media test: the program, the run notes, and the logs.

Run `python3 seagate-media-test.py --help` for the full how-to. The commands are:

- `python3 seagate-media-test.py plan` shows how many more 499,998,720-byte files fit if 30, 40, or 50 decimal GB stay free.
- `python3 seagate-media-test.py run --groups 9` writes and reads nine more sets of 500. It skips finished names and will not start a second writer.
- `python3 seagate-media-test.py watch` follows the logs. Stopping it does not stop the writer.
- `python3 seagate-media-test.py status` shows the writer, the last log line, the warning count, and the error count.
- `python3 seagate-media-test.py classify` sorts the current detail log into the normal, warning, and error logs. It does not start a writer.

`seagate-media-test.c` is the test. The Python script compiles it to `seagate-media-test-bin` when the source is newer. Run the Python script. It will not start while a writer is already running.

A run you start with this version writes three logs:

- `seagate-normal.log` is everything that is fine, including a slow write.
- `seagate-warnings.log` is a read of 4.000 seconds or more that still matched.
- `seagate-errors.log` is a mismatch, a partial file, a rename failure, or any I/O of 15.000 seconds or more.

The run already in progress keeps its own copies in `seagate-screen.log` and `seagate-detail.log`. `python3 seagate-media-test.py classify` sorts that detail log into the three logs above. It does not start a writer.

`SEAGATE-8TB-HANDOFF.md` is the resume note. Read it before starting anything.

One writer at a time. Do not delete a short `untested area` file. Do not fill the volume to 0 bytes free.
