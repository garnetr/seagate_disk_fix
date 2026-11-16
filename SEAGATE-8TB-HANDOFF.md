# Seagate 8TB handoff

Written 2026-11-15. Updated 2026-11-16 for version 0.91. Read this before touching the drive, ending the test, or starting another one.

## Finish this yourself (version 0.91)

The test that is already running finishes on its own. Leave it alone. Do not start a second writer. Do not watch it from a chat session. The program and the notes are in this folder:

`/Users/garnetchaney/fix/seagate_disk_fix`

Version 0.91 is the copy you run. The public repo is https://github.com/garnetr/seagate_disk_fix and the tag is `v0.91`.

What is running now, and must keep running:

- Writer pid 68132, parent pid 1: `/tmp/seagate-groups-15610`
- `caffeinate` pid 68133, child of the writer
- Log copier pid 79128: `seagate-media-test.py _follow` in this folder
- Range: files 11111–15610, nine groups of 500. Stop at 15610.
- When this note was written, group 5 of 9 (files 13111–13610) was still on its first pass. The last line in `seagate-screen.log` was `READ 13561-13570`, elapsed 75 min 12 s into group 5, `bad=0`. The copier has kept appending after that line.

That writer is the older binary. It does not know about the version 0.91 log split. Its screen copy is `seagate-screen.log`. Its per-file copy is `seagate-detail.log`. Both are in this folder, so they survive a reboot of the Mac even though `/tmp` does not. `seagate-errors.log` is for real failures from that run. A slow read is not written there.

Check it without starting anything:

```bash
cd /Users/garnetchaney/fix/seagate_disk_fix
python3 seagate-media-test.py status
```

Sort the detail log into the three version 0.91 logs when you want that view. This reads a log file. It does not start a writer:

```bash
python3 seagate-media-test.py classify
```

- `seagate-normal.log` — fine results, including a slow write and a file that only needs its second read
- `seagate-warnings.log` — a read or second read of 4.000 seconds or more that still matched. It is not a failure. A matching second read does not get a third read.
- `seagate-errors.log` — a mismatch, a partial file left in place, a rename failure, a non-zero bad count, or any single-file I/O of 15.000 seconds or more

To watch the logs yourself, `python3 seagate-media-test.py watch`. Stopping that tail does not stop the writer.

When pid 68132 is gone, the copier appends one `# follow stopped` line and exits. The names on `/Volumes/2020 Seagate 8TB` are the record that survives. Do not start `run` until `status` says no writer is running. A later run uses version 0.91 and writes the three logs directly:

```bash
python3 seagate-media-test.py plan
python3 seagate-media-test.py run --groups N
```

`plan` is how many more files fit at a 30, 40, or 50 GB reserve. Filling to the last byte is too tight. This run still stops at file 15610. Do not pass 15610 unless you decide to.

Leave these alone:

- One writer only. The script refuses to start a second one.
- `untested area 11002` is short, 352,321,536 bytes. Do not delete it.
- Files 00001–00600 are solid 0xFF from an older program. A finished name is skipped.
- Files 01138 and 01244 still need a cold re-read. Their earlier reads were fast enough to be the OS cache. Do that only while no writer is running.
- Do not turn Wi-Fi on. The working path is the USB Ethernet adapter.
- Do not erase the disk, run First Aid, run fsck, or rewrite a file that already passed.

The older sections below are the record of how the drive got here. The instructions in this section are the ones to follow.

## Run in progress: files 11111–15610

Nine groups of 500. Same pattern, same 499,998,720-byte size, same `F_NOCACHE` and `F_FULLFSYNC` rules. A write of 4.5 seconds or more makes that ten get read before the next ten is written. After each group of 500, every `good but slow` file in that group is read a second time. The program skips a finished name, so running it again continues. It does not touch the short file `untested area 11002`.

- Program: `/tmp/seagate-groups-15610` (source `/tmp/seagate-groups-15610.c`)
- Writer pid 68132, parent pid 1, so it is detached from the launcher. `caffeinate` pid 68133.
- Log: `/tmp/seagate-groups-15610.txt`
- Stdout: `/tmp/seagate-groups-15610.stdout`
- Write times: `/tmp/seagate-groups-15610-times.txt`
- `MAXF` is 17000. Do not rerun the older binary. Its table stopped at 12000 and would drop the slow rule for these file numbers.

Do not start a second writer while pid 68132 is alive. This run ends at file 15610. That is 98 files short of the 4,598-file recount, so about 89 GB should remain free. Do not continue past 15610 unless asked.

## Run finished: files 06111–11110

The program printed `ALL DONE files=5000 elapsed_s=1475 bad=1`. That clock is only the resumed process, 24 minutes 34 seconds. The writer is not running.

The first launch, pid 52730, finished groups 1–9 and wrote group 10 through file 11001. The 10-hour command limit then killed it while writing file 11002. The resume, pid 65425, skipped finished names and finished group 10. File 11001 was read after the resume, in 4.009 s, and is `good area 11001`.

`read_bad=0` and `second_bad=0`. No file was renamed `failed` or `failed second read`. No read mismatched. The one bad count is `untested area 11002`, short at 352,321,536 bytes, left in place from that kill. Do not delete it unless asked to finish that partial.

Group 10 has 84 files named `good twice but slow`, confirmed on the volume. No `good but slow` name remains. The numbers are 10615, 10643, 10645, 10646, 10647, 10651, 10658, 10664, 10665, 10666, 10684, 10685, 10696, 10702, 10728, 10740, 10745, 10751, 10757, 10758, 10763, 10770, 10775, 10805, 10808, 10809, 10815, 10820, 10827, 10832, 10839, 10844, 10848, 10856, 10862, 10869, 10881, 10882, 10893, 10894, 10902, 10906, 10911, 10912, 10918, 10920, 10922, 10929, 10931, 10935, 10947, 10952, 10957, 10959, 10964, 10967, 10973, 10976, 10980, 10981, 10988, 10994, 10995, 11003, 11008, 11014, 11027, 11028, 11032, 11039, 11042, 11043, 11044, 11056, 11057, 11061, 11068, 11073, 11078, 11083, 11086, 11092, 11097, and 11103.

Groups 1–9 of this same run had already finished with every bad count at 0. Their `good twice but slow` counts are 1, 2, 4, 7, 6, 12, 30, 25, and 50. Together with the 18 from files 00625–01052 and the 11 from files 01111–06110, the volume holds 250 `good twice but slow` files.

About 2.28 TB is free (2,284,457,964 KB). That is roughly 4,600 more files of this size if a few tens of GB stay free. Recount before the last stretch. The old 15,900-file figure was for an empty volume. Do not start file 11111 unless asked.

Log: `/tmp/seagate-groups-11110.txt`. Stdout: `/tmp/seagate-groups-11110.stdout`. `/tmp` is lost on reboot. The names on the volume are the resume record.

## Ten groups finished

Files `01111`–`06110` were written and read in ten groups of 500. Same pattern, same 499,998,720-byte size, same `F_NOCACHE` and `F_FULLFSYNC` rules. The program exited 0. Stdout ended with `ALL DONE files=5000 elapsed_s=30901 bad=0` (8 hours 35 minutes). Every group reported `write_bad=0 read_bad=0 second_bad=0`. No file was renamed `failed` or `failed second read`.

Eleven writes in this run were 4.5 seconds or longer. Each passed its first read and its second read and is `good twice but slow`:

| File | Write seconds |
| --- | ---: |
| 01111 | 4.910 |
| 01251 | 5.104 |
| 01252 | 5.581 |
| 01265 | 8.958 |
| 01538 | 5.659 |
| 01540 | 4.642 |
| 03195 | 7.327 |
| 03860 | 7.371 |
| 04519 | 6.643 |
| 04520 | 9.637 |
| 04521 | 8.251 |

Groups 2, 3, 4, 8, 9, and 10 had no write at or above 4.5 seconds, so each printed `SECOND NONE`.

Reads at or above 4.0 seconds that still matched, and whose writes were under 4.5 seconds, stayed `good area`: 01790 (4.034 s), 01793 (4.681 s), 01796 (4.033 s), 01803 (4.143 s), 01806 (4.107 s), 03475 (4.350 s), 03851 (4.378 s), 04511 (4.103 s), 04512 (5.224 s), 04513 (4.279 s), 04514 (4.165 s), 04518 (4.285 s), 04646 (4.028 s), 04647 (4.341 s), 05281 (4.553 s), 05886 (4.369 s), 05887 (4.308 s). Files 04519 and 04520 also had slow first reads and are in the `good twice but slow` list above.

Two first reads were fast enough to be OS cache, and they still matched: 01138 in 0.169 s (about 2,960 MB/s) and 01244 in 1.305 s (about 383 MB/s). Both are `good area`. They still need a later cold re-read. Do not start that while another writer is running.

- Program: `/tmp/seagate-groups-5000` (source `/tmp/seagate-groups-5000.c`). It has exited. Do not start it again unless the user asks for more files.
- Log: `/tmp/seagate-groups-5000.txt`
- Stdout copy: `/tmp/seagate-groups-5000.stdout`
- Write times: `/tmp/seagate-groups-times.txt`

`/tmp` is lost on reboot. The names on the volume are the resume record. Files `00001`–`11110` are finished, except the short file `untested area 11002`. Pid 68132 is writing `11111`–`15610`. Do not start a second writer while it is alive.

`WIFI-HANDOFF.md` is a separate Wi-Fi problem. Leave Wi-Fi off until the user asks. Its note that a rescue copy is still running is out of date. The copy finished on Sat Nov 7 12:18:09 PST 2026. The media test is finished through file `11110`. About 2.28 TB is still untested.

## If the test was stopped

The files on `/Volumes/2020 Seagate 8TB` are the record that survives a reboot. Programs and logs under `/tmp` do not.

Do not erase the disk, run First Aid, run fsck, delete a test file, or rewrite a file that already passed. Do not touch the 10 TB drive or the 12 TB drive. Disk numbers change after a reboot. Identify this drive by the name and size below before any command that uses `disk2` or `disk5`.

A writer may be running. Confirm before starting another batch:

```bash
pgrep -lf 'seagate-groups-11110|seagate-groups-5000|seagate-pattern-500|seagate-slow-watch'
```

If a writer is running, leave it alone. If nothing is running, continue from the names on the volume:

1. Mount the volume. It should be `/Volumes/2020 Seagate 8TB`. Confirm it is the 8.0 TB Backup+ Hub BK, media size 8,001,563,221,504 bytes, not the 10 TB or 12 TB disk.
2. Every finished test file is exactly 499,998,720 bytes. A shorter file is an unfinished write. Leave it in place. Do not delete it. Record the name and size, and ask before removing it. A new file must use the next free number, not reuse that number, unless the user says to finish the partial.
3. `good area NNNNN` has passed one full read. Leave it.
4. `good but slow NNNNN` passed one full read and was a slow write. It still needs the second read described below.
5. `good twice but slow NNNNN` passed the write and two reads. Leave it.
6. `failed NNNNN` failed its first read. Leave it.
7. `failed second read NNNNN` passed the first read and failed the second. Leave it.
8. `untested area NNNNN` at the full size still needs its first read. Compare it with the pattern for that file number. On a match, rename a slow file to `good but slow NNNNN` and any other file to `good area NNNNN`. On a mismatch, rename it to `failed NNNNN`. The rename has to be on this same volume so the bytes stay where they were written.
9. After every file from this batch has had its first read, second-read every `good but slow` file. On a match, rename it to `good twice but slow NNNNN`. On a mismatch, rename it to `failed second read NNNNN`.
10. The next new file is one higher than the highest number already on the volume. Do not reuse a number.

The slow-write rule for the next batch is in "How to continue" below. This batch of 500 was already in its read pass when that rule was added, so its first read is the full pass that was already running.

## Which drive

- Product: Seagate Backup+ Hub BK, USB vendor `0x0BC2`, product `0xAB38`
- Serial recorded during diagnosis: `NA9QC392`. Check it again with USB system info before any erase. Do not erase by disk number alone.
- Physical media size: 8,001,563,221,504 bytes
- At this writing the physical disk was `disk2`, the APFS container was `disk5` (store `disk2s2`), and the volume was `disk5s1`
- Volume name: `2020 Seagate 8TB`
- Mount: `/Volumes/2020 Seagate 8TB`
- Format now: GUID partition map, one APFS volume, case-insensitive
- Container size: 8,001,353,465,856 bytes
- SMART is not supported through this bridge
- The other external disks at this writing were `disk3` (10 TB Seagate Backup+ Hub) and `disk6` (12 TB WD, including `Win2026A`). The rescue copy lives on the 10 TB volume `/Volumes/2022-10TB Writeable/Seagate 8TB External 2020/`

## What was moved off

The old volume was named `Seagate 8TB External 2020`. It was readable and not writable. macOS had already said it could not repair that disk. The user later ran Disk Utility First Aid. First Aid failed.

The rescue copy used `/usr/bin/rsync -aE --partial --stats` from `/Volumes/Seagate 8TB External 2020/` onto `/Volumes/2022-10TB Writeable/Seagate 8TB External 2020/`. It finished with `EXIT:23` and `END Sat Nov 7 12:18:09 PST 2026`. Exit 23 means some paths failed. It is not a checksum proof. The log was `/tmp/seagate-rsync.log` (about 5.1 GB) and may be gone after a reboot.

Recorded rsync totals for that run:

- Files considered: 7,249,064
- Files transferred: 5,989,826
- Total file size, including files already at the destination: 2,288,314,370,624 bytes
- Transferred file size: 787,138,968,112 bytes
- Literal data written by that run: 770,236,528,892 bytes
- Overall rate about 20 MB/s

Already-copied destination files were left in place and skipped by size and time. Nothing at the destination was deleted to make room.

Left behind on purpose:

- `/Backups.backupdb` (Time Machine). The user accepted that this would be destroyed by the erase.
- Dropbox folders that were already on NAS-2021-A, plus `/FromNAS200/Garnet Music`, `/projects/Laughter`, and eight artists under Music.Archived (Beyonce, Fleetwood Mac, Genesis, Jennifer Lopez, LeToya, Leto - Russian Pop, `_foreign`, `_unsorted`).
- Four unreadable VM bundles under `/Virtual Machines/MacBook2014/`: `CentOS 64-bit.vmwarevm`, `CentOS 7 64-bit.vmwarevm`, `Ubuntu 64-bit.vmwarevm`, and `Windows XP Professional.vmwarevm`. A bad slice makes the whole bundle useless. Those slices were mode `rw-------` uid 504. The vmdk bytes in those four bundles were about 78.3 GB, and the bundles were about 84.6 GB.
- `/DropBox/current/Dropbox/For Clients/Paul Curtis/First Flight/DJI_0925.MP4` (3,856,935,862 bytes). A partial copy was entirely zeros. The copy was stopped and the partial destination removed.
- `/Pictures/MacBook2014/Photos Library.photoslibrary/Masters/2015/12/08/20151208-064808/IMG_0797.MOV` (10,642,587,410 bytes, mode 600, uid 504). It could not be read.

The old volume also had an unused High Sierra restore volume, `ASRNewVolume_5569`. It was not useful for this Mac. Erasing the whole disk removed it. There was no separate low-level wipe.

A second full rsync was not run. Do not start one unless the user asks. The source volume no longer exists.

## Failure mode

A weak area does not always return an error. A read of a bad spot can succeed, take exactly 15.000 seconds, and come back as zeros. This happened for reads as small as 32 bytes. A later read of zeros cannot tell a real zero file from this failure, so a zero-fill of the disk would hide the bad spots.

Fast regions returned real data. Large files that were checked (zip with `PK`, ISO with `CD001` at offset 32768, mp4/mov `ftyp`) were real. One known-zero file was `FamilyHealthGuideCookingSection.pdf`, 206,658,067 bytes, all zeros. Real copies of the zeroed books and health PDFs that were checked were on the NAS or on `/Volumes/Backups/Dropbox Goodsync/`.

The failing Hub was using UASP (protocol 98 / `0x62`). The healthy 10 TB Hub was using BOT (protocol 80 / `0x50`). After the erase, good areas of this same disk write at about 130–170 MB/s and read at about 170–190 MB/s. The old rescue speed of about 20 MB/s was the damaged filesystem and weak media, not the limit of a healthy stretch.

A healthy 500 MB file on the outer tracks writes in about 2.7–3.5 seconds and reads in about 2.5–3.4 seconds. Inner tracks can be somewhat slower and still be fine. A bad spot is a multi-second stall inside one chunk, or a read that returns zeros or the wrong pattern. One finished write of 5–8 seconds is slow, not yet a failed file. The old 15-second zero read is the failure to catch.

`sudo -n` does not work on this Mac. Do not ask the user to paste a password.

## Repartition

The whole physical disk was erased, not one slice. `diskutil eraseDisk APFS "Seagate 8TB" GPT disk2` failed once because `mds_stores` had the disk open. `diskutil unmountDisk force disk2` and then the same erase succeeded. The user renamed the new volume to `2020 Seagate 8TB`.

The map is GUID. There is an EFI partition and one APFS container with one volume. No full-disk zero was written. The erase replaced the partition map and the filesystem only. Old bytes may still be on the platters until a test file is written over them.

## How the media test works

Empty preallocation does not touch the media. A file counts only after a full non-zero write, a flush past the OS cache and the drive cache, and a full read that matches the pattern.

Each file is 499,998,720 bytes. That is 500,000,000 rounded down to a multiple of 4096, because uncached I/O on macOS rejects any other length. Writes and reads use `F_NOCACHE` and page-aligned buffers from `posix_memalign`. The write ends with `F_FULLFSYNC`. Compare with `memcmp` against the expected pattern. A rename on this volume does not move the extents. Do not rewrite a passed file, and do not clone a good file onto a suspect hole.

Files `00001` through `00600` are filled with the byte `0xFF`. That pattern catches the 15-second zero read. It cannot tell two files apart, because every file is the same bytes.

Files `00601` onward use a per-file pattern. No byte is `0`. For file number `N` and a 4096-byte page whose index is `P` (`P` starts at 0):

- The fill byte is `((N * 17) % 255) + 1`.
- The first two bytes are `N` in base 255, least significant digit first. Digit `d` is stored as the byte `d + 1`, so a zero digit is the byte 1.
- The next three bytes are `P` in the same base-255 encoding.
- The rest of the page is the fill byte.

Regenerate that pattern and compare. A mismatch means the file failed, even if the drive returned a success status.

A write of 4.5 seconds or longer is slow. These files were over that line but under 4.5, and they stay `good area` unless the user lowers the line: `00622` 4.278 s, `00628` 4.123 s, `00629` 4.475 s, `00630` 4.465 s, `00631` 4.310 s.

On a future batch, when any file in a group of ten is slow:

- Read all ten of that group before writing the next group.
- A slow file that matches becomes `good but slow NNNNN`.
- Any file that does not match becomes `failed NNNNN`.
- A file in that ten that was not slow, and matches, becomes `good area NNNNN`.
- When the whole batch of 100 or 500 has finished its first reads, read each `good but slow` file again. A match becomes `good twice but slow NNNNN`. A mismatch becomes `failed second read NNNNN`.

Do not delete passed files, slow files, or failed files while the disk is being filled. The used space is what keeps later writes from landing in an untested hole. Leave several gigabytes free so APFS can still rename and delete. The working stop is about 15,900 files of this size, not 16,000. 16,000 files would leave only about 500 MB. Check `df` before the last stretch and stop while a few GB are still free.

## Results already finished

Files `00001`–`00100`, all `0xFF`, written and read with no mismatches. Writes: 100 files, min 2.703 s, median 3.566 s, max 5.052 s, mean 3.598 s. Reads: min 2.397 s, median 2.486 s, max 2.961 s, mean 2.490 s. They are `good area 00001` through `good area 00100`.

Files `00101`–`00600`, all `0xFF`, written and read with no mismatches. Writes: min 2.651 s, median 3.531 s, max 8.721 s. Reads: min 2.480 s, median 2.795 s, max 3.381 s, 500 files, no bad bytes. They are `good area` except the four slow files below that were renamed after this rule was added.

The slow `0xFF` writes in that set were `00456` at 7.383 s, `00514` at 8.721 s, and `00515` at 8.290 s. Their later full reads were in the normal 2.6–3.4 s range and matched. They stayed `good area` because the slow-name rule applies to the patterned batch onward. Do not rewrite them.

Files `00601`–`00610` were the ten-file trial of the per-file pattern. All ten matched. Mean write 3.240 s (min 2.659, max 4.398). Mean read 3.001 s (min 2.655, max 3.358). The pattern did not change the speed. They are `good area 00601` through `good area 00610`.

## The run that was in progress

Files `00611`–`01110`, per-file pattern. All 500 writes finished with no write errors. Write summary: min 2.663 s, median 3.028 s, max 7.018 s, elapsed 1578 s. The read pass started at 02:28:39. When this file was written, the read had completed through `00850` with no mismatches. Read speed was about 2.5–3.1 s per file, about 178–190 MB/s.

That read later finished with no mismatches, and the second read of the 18 slow files also matched. Those 500 files are `good area`, except the 18 listed below, which are `good twice but slow`.

Log: `/tmp/seagate-pattern-500.txt`. One line of that log, `flush_s=0.000`, is a logging bug. The `total_s` number includes the drive flush. Do not treat `flush_s` from this log as a measurement.

Programs, lost on reboot, so rewrite them from this file if `/tmp` is gone:

- `/tmp/seagate-pattern-500.c` and `/tmp/seagate-pattern-500`
- `/tmp/seagate-second-read.c` and `/tmp/seagate-second-read`
- `/tmp/seagate-slow-watch.py`

The watcher renames a slow file from `good area` to `good but slow` when the first read passes, then runs `/tmp/seagate-second-read` on those files after `READ DONE`.

These 18 writes were 4.5 s or slower. All 18 later passed a first read and a second read. They are `good twice but slow`. The table below records the write times. The "name at handoff" column is the name at the moment this section was first written, and it is no longer the live name:

| File | Write seconds | Name at handoff |
| --- | ---: | --- |
| 00625 | 5.040 | good but slow |
| 00626 | 4.576 | good but slow |
| 00627 | 5.217 | good but slow |
| 00633 | 5.595 | good but slow |
| 01037 | 4.719 | untested, waiting for first read |
| 01038 | 5.958 | untested, waiting for first read |
| 01039 | 7.018 | untested, waiting for first read |
| 01040 | 5.348 | untested, waiting for first read |
| 01041 | 5.305 | untested, waiting for first read |
| 01042 | 5.865 | untested, waiting for first read |
| 01043 | 6.076 | untested, waiting for first read |
| 01044 | 4.563 | untested, waiting for first read |
| 01045 | 5.083 | untested, waiting for first read |
| 01048 | 5.630 | untested, waiting for first read |
| 01049 | 5.491 | untested, waiting for first read |
| 01050 | 6.177 | untested, waiting for first read |
| 01051 | 6.200 | untested, waiting for first read |
| 01052 | 5.195 | untested, waiting for first read |

`01046` and `01047` sit in that slow stretch and were under 4.5 s. They follow the normal `good area` rule.

At the handoff snapshot the volume held 1,110 test files, each exactly 499,998,720 bytes: 798 named `good area`, 4 named `good but slow`, and 308 named `untested area`. That count moved as soon as the next read finished. Trust the live names, then the log.

## How to continue

Files `00001`–`11110` are finished, except the short file `untested area 11002`. A writer is running for `11111`–`15610` (pid 68132). Leave it alone. Do not start file `15611` unless the user asks.

1. The current run is `11111`–`15610`, pid 68132. If that pid is gone before file `15610` is finished, rerun `/tmp/seagate-groups-15610`. It skips finished names. Leave `untested area 11002` in place unless the user says to remove that partial and write the number again. The next file after `15610` is `15611`. Use the per-file pattern, the same size, `F_NOCACHE`, and `F_FULLFSYNC`.
2. A group of ten that contains a write of 4.5 s or more is read immediately, before the next ten are written. Apply the slow and failed names at that read. At the end of the batch, second-read only the `good but slow` files.
3. Keep going in batches the user asks for until about 15,900 files are on the volume. Then stop with a few GB free. Recalculate free space before the last stretch.
4. Only after the user agrees that the first pass is done: delete one suspect file at a time and fill that hole with smaller files of about 32 MB, using the same non-zero pattern, flush, and read. Keep the ones that pass. Do not use 32 KB files for that step. Do not clone a good file into the hole.
5. A later cold re-read of `01138` and `01244` is still open. Do it only when no writer is running.

## Do not

- Do not reboot, erase, or run First Aid while a test is unfinished. Pid 68132 is writing `11111`–`15610`. Do not start file `15611` unless asked.
- Do not delete a test file to "clean up."
- Do not fill the volume to zero bytes free.
- Do not treat a fast write as proof. The read has to match.
- Do not treat a zero read as a real empty file.
- Do not update the QNAP, swap NAS disks, or turn Wi-Fi on as part of this test.

## FAQ

**I noticed that when I used xxd to look at some of these files, there were large sections of the same byte, and then a periodic different byte. How often are the different bytes, and how far apart are they spaced?**

The different bytes are a 5-byte header at the start of every 4,096-byte page. The other 4,091 bytes of that page are one fill byte, repeated. The next header begins 4,096 bytes later, at offset `0x1000`, then `0x2000`, and so on.

In `xxd`, which prints 16 bytes per line, that is one unusual line followed by 255 lines of the same byte, then the next unusual line.

Those five bytes are:

- Bytes 0–1 of the page: the file number, in base 255, least-significant digit first. Digit `d` is stored as the byte `d + 1`.
- Bytes 2–4 of the page: the page number, starting at 0, in the same encoding.

The byte that changes every page is byte 2. It steps by one until 255, then wraps and byte 3 advances. Bytes 0 and 1 stay the same for the whole file.

The fill byte is constant for one file: `((file number × 17) % 255) + 1`. For file 601 that is `0x12`, and the file starts `5c 03 01 01 01` followed by `0x12` until offset `0x1000`, where the header is `5c 03 02 01 01`. A header byte can equal the fill byte, so fewer than five bytes may look different.

Files 1–600 are solid `0xFF` and do not have these headers. The page markers start at file 601.
