/* Seagate 8TB media test.
 *
 * This is the program that has been writing and reading the patterned files
 * on /Volumes/2020 Seagate 8TB. Run it through seagate-media-test.py in this
 * folder. That wrapper is what sets the file range, the logs, and caffeinate.
 * Do not start this binary by hand while another copy is already running.
 *
 * Each file is (500000000 / 4096) * 4096 = 499998720 bytes. The write and the
 * read are uncached, and the write is followed by F_FULLFSYNC. The pattern is
 * not a zero fill. Fill byte is ((file_number * 17) % 255) + 1. Each 4096-byte
 * page starts with a 5-byte header: the file number in two base-255 digits,
 * then the 0-based page index in three base-255 digits, least-significant
 * digit first. A digit d is stored as d+1. The other 4091 bytes are the fill.
 *
 * A finished name is left alone. A short "untested area" file is left in place
 * and counted as a bad write. It is not deleted and not rewritten.
 *
 * A write of slow_sec or more (4.5 in the runs so far) makes that ten get read
 * at once. A match is renamed "good but slow N". Any other match in that ten
 * is "good area N". A mismatch is "failed N". After the group, only the
 * "good but slow" names are read again. A match becomes "good twice but slow N".
 * A second read that matches does not get a third read.
 *
 * Screen lines go to stdout. The same lines, plus one line per file, go to the
 * detail log. The error log gets only real failures and a single file I/O of
 * 15 seconds or more. Needing a second read is not an error.
 *
 * Arguments:
 *   seagate-media-test-bin VOLUME FIRST GROUPS PER SLOW_SEC DETAIL TIMES ERRORS MAXF
 *
 * FIRST is the first file number. GROUPS sets of PER files are visited.
 * PER must be a multiple of 10. MAXF is one past the highest file number whose
 * write time is stored. The whole range must end below MAXF. The Python
 * wrapper raises MAXF so that a requested range still remembers every slow write.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <sys/fcntl.h>

#define SIZE (((500000000u / 4096u) * 4096u))
#define CHUNK (4u * 1024u * 1024u)
#define PAGE 4096u
#define STALL_SEC 15.0

enum { ST_MISSING, ST_PARTIAL, ST_UNTESTED, ST_GOOD, ST_SLOW, ST_TWICE, ST_FAIL, ST_FAIL2 };

static FILE *logf;
static FILE *errf;
static const char *vol = "/Volumes/2020 Seagate 8TB";
static double slow_sec = 4.5;
static unsigned maxf = 20000;
static double *time_of;
static char time_path[512];

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static void log_line(const char *line) {
    fputs(line, logf);
    fputc('\n', logf);
    fflush(logf);
}

static void note_error(const char *line) {
    if (!errf)
        return;
    fputs(line, errf);
    fputc('\n', errf);
    fflush(errf);
}

static int field_int(const char *line, const char *key, int *out) {
    const char *p = strstr(line, key);
    if (!p)
        return 0;
    return sscanf(p + strlen(key), "%d", out) == 1;
}

static int field_double(const char *line, const char *key, double *out) {
    const char *p = strstr(line, key);
    if (!p)
        return 0;
    return sscanf(p + strlen(key), "%lf", out) == 1;
}

/* A slow file that only needs a second read is not an error.
 * Copy a summary only when a file failed, or when one I/O reached the
 * 15 second USB-bridge stall. */
static int summary_is_error(const char *line) {
    double maxs;
    int bad, wb, rb, sb;
    if (field_double(line, " max_s=", &maxs) && maxs >= STALL_SEC)
        return 1;
    if (field_int(line, " bad=", &bad) && bad != 0)
        return 1;
    if (strncmp(line, "GROUP ", 6) == 0 && strstr(line, " DONE ") &&
        field_int(line, " write_bad=", &wb) &&
        field_int(line, " read_bad=", &rb) &&
        field_int(line, " second_bad=", &sb) &&
        (wb || rb || sb))
        return 1;
    return 0;
}

static void show(const char *line) {
    log_line(line);
    puts(line);
    fflush(stdout);
    if (strncmp(line, "BAD ", 4) == 0 || summary_is_error(line))
        note_error(line);
}

static uint8_t fill_byte(unsigned file_no) {
    return (uint8_t)(((file_no * 17u) % 255u) + 1u);
}

static void put255(uint8_t *p, uint32_t v, int digits) {
    for (int i = 0; i < digits; i++) {
        p[i] = (uint8_t)((v % 255u) + 1u);
        v /= 255u;
    }
}

static void fill_pattern(uint8_t *buf, size_t n, unsigned file_no, uint64_t off) {
    memset(buf, fill_byte(file_no), n);
    uint64_t page = off / PAGE;
    for (size_t i = 0; i + 5 <= n; i += PAGE, page++) {
        put255(buf + i, file_no, 2);
        put255(buf + i + 2, (uint32_t)page, 3);
    }
}

static int cmp_double(const void *a, const void *b) {
    double da = *(const double *)a;
    double db = *(const double *)b;
    return (da > db) - (da < db);
}

static void batch_line(char *out, size_t outlen, const char *phase,
                       const unsigned *nums, const double *secs, int n,
                       int bad, double elapsed) {
    double s[16];
    double sum = 0;
    if (n < 1 || n > 16) {
        snprintf(out, outlen, "BAD BATCH %s n=%d", phase, n);
        return;
    }
    for (int i = 0; i < n; i++) {
        s[i] = secs[i];
        sum += secs[i];
    }
    qsort(s, (size_t)n, sizeof s[0], cmp_double);
    double median = (n % 2) ? s[n / 2] : (s[n / 2 - 1] + s[n / 2]) / 2.0;
    double mean = sum / n;
    double mbps = mean > 0.001 ? (SIZE / 1e6) / mean : 0;
    snprintf(out, outlen,
             "%s %05u-%05u min_s=%.3f median_s=%.3f mean_s=%.3f max_s=%.3f "
             "MBps=%.1f elapsed_s=%.0f bad=%d",
             phase, nums[0], nums[n - 1], s[0], median, mean, s[n - 1],
             mbps, elapsed, bad);
}

static void path_for(char *out, size_t n, const char *prefix, unsigned num) {
    snprintf(out, n, "%s/%s %05u", vol, prefix, num);
}

static int full_file(const char *path) {
    struct stat st;
    if (stat(path, &st) != 0)
        return 0;
    return st.st_size == (off_t)SIZE;
}

static int any_file(const char *path) {
    struct stat st;
    return stat(path, &st) == 0;
}

static int classify(unsigned num) {
    char p[512];
    path_for(p, sizeof p, "good twice but slow", num);
    if (any_file(p))
        return ST_TWICE;
    path_for(p, sizeof p, "failed second read", num);
    if (any_file(p))
        return ST_FAIL2;
    path_for(p, sizeof p, "good but slow", num);
    if (any_file(p))
        return ST_SLOW;
    path_for(p, sizeof p, "good area", num);
    if (any_file(p))
        return ST_GOOD;
    path_for(p, sizeof p, "failed", num);
    if (any_file(p))
        return ST_FAIL;
    path_for(p, sizeof p, "untested area", num);
    if (full_file(p))
        return ST_UNTESTED;
    if (any_file(p))
        return ST_PARTIAL;
    return ST_MISSING;
}

static void remember_time(unsigned num, double secs) {
    if (num < maxf)
        time_of[num] = secs;
    FILE *f = fopen(time_path, "a");
    if (!f)
        return;
    fprintf(f, "%u %.3f\n", num, secs);
    fclose(f);
}

static void load_times(void) {
    for (unsigned i = 0; i < maxf; i++)
        time_of[i] = -1;
    FILE *f = fopen(time_path, "r");
    if (!f)
        return;
    unsigned num;
    double secs;
    while (fscanf(f, "%u %lf", &num, &secs) == 2) {
        if (num < maxf)
            time_of[num] = secs;
    }
    fclose(f);
}

static void note_stall(const char *kind, unsigned num, double secs) {
    char line[256];
    if (secs < STALL_SEC)
        return;
    snprintf(line, sizeof line,
             "STALL %s %05u seconds=%.3f MBps=%.1f bytes matched",
             kind, num, secs, secs > 0.001 ? (SIZE / 1e6) / secs : 0);
    note_error(line);
}

static int write_one(const char *path, unsigned file_no, double *total_s) {
    int fd = open(path, O_CREAT | O_RDWR | O_EXCL, 0644);
    if (fd < 0)
        return -1;
    if (fcntl(fd, F_NOCACHE, 1) != 0) {
        close(fd);
        return -1;
    }
    void *buf = NULL;
    if (posix_memalign(&buf, PAGE, CHUNK) != 0) {
        close(fd);
        return -1;
    }
    double t0 = now();
    uint64_t done = 0;
    int rc = 0;
    while (done < SIZE) {
        size_t n = CHUNK;
        if (SIZE - done < n)
            n = (size_t)(SIZE - done);
        fill_pattern(buf, n, file_no, done);
        size_t wrote = 0;
        while (wrote < n) {
            ssize_t w = write(fd, (uint8_t *)buf + wrote, n - wrote);
            if (w <= 0) {
                if (w < 0 && errno == EINTR)
                    continue;
                if (w == 0)
                    errno = EIO;
                rc = -1;
                break;
            }
            wrote += (size_t)w;
        }
        if (rc != 0)
            break;
        done += n;
    }
    if (rc == 0 && fcntl(fd, F_FULLFSYNC) != 0)
        rc = -1;
    *total_s = now() - t0;
    free(buf);
    close(fd);
    if (rc == 0 && done != SIZE) {
        errno = EIO;
        return -1;
    }
    return rc;
}

static int read_one(const char *path, unsigned file_no, double *read_s, unsigned long long *bad) {
    int fd = open(path, O_RDONLY);
    if (fd < 0)
        return -1;
    if (fcntl(fd, F_NOCACHE, 1) != 0) {
        close(fd);
        return -1;
    }
    void *got = NULL;
    void *exp = NULL;
    if (posix_memalign(&got, PAGE, CHUNK) != 0 || posix_memalign(&exp, PAGE, CHUNK) != 0) {
        free(got);
        close(fd);
        return -1;
    }
    double t0 = now();
    uint64_t done = 0;
    unsigned long long mismatches = 0;
    int rc = 0;
    while (done < SIZE) {
        size_t n = CHUNK;
        if (SIZE - done < n)
            n = (size_t)(SIZE - done);
        size_t gotn = 0;
        while (gotn < n) {
            ssize_t r = read(fd, (uint8_t *)got + gotn, n - gotn);
            if (r < 0) {
                if (errno == EINTR)
                    continue;
                rc = -1;
                break;
            }
            if (r == 0)
                break;
            gotn += (size_t)r;
        }
        if (rc != 0)
            break;
        fill_pattern(exp, n, file_no, done);
        if (gotn != n) {
            mismatches += (n - gotn);
            rc = -1;
        }
        size_t lim = gotn < n ? gotn : n;
        if (memcmp(got, exp, lim) != 0) {
            for (size_t i = 0; i < lim; i++) {
                if (((uint8_t *)got)[i] != ((uint8_t *)exp)[i])
                    mismatches++;
            }
        }
        done += gotn;
        if (gotn == 0)
            break;
    }
    *read_s = now() - t0;
    *bad = mismatches;
    free(got);
    free(exp);
    close(fd);
    if (rc != 0 || done != SIZE || mismatches != 0) {
        if (mismatches == 0 && done != SIZE)
            *bad = SIZE - done;
        return -1;
    }
    return 0;
}

static int read_first(unsigned num, double *secs) {
    char src[512], dst[512], line[256];
    path_for(src, sizeof src, "untested area", num);
    if (!full_file(src))
        return 1;
    double read_s = 0;
    unsigned long long bad = 0;
    int rc = read_one(src, num, &read_s, &bad);
    *secs = read_s;
    int slow = num < maxf && time_of[num] >= slow_sec;
    if (rc != 0) {
        path_for(dst, sizeof dst, "failed", num);
        if (rename(src, dst) != 0)
            snprintf(line, sizeof line, "BAD R %05u read_s=%.3f bad_bytes=%llu rename_errno=%d",
                     num, read_s, bad, errno);
        else
            snprintf(line, sizeof line, "BAD R %05u read_s=%.3f bad_bytes=%llu", num, read_s, bad);
        show(line);
        return -1;
    }
    path_for(dst, sizeof dst, slow ? "good but slow" : "good area", num);
    if (rename(src, dst) != 0) {
        snprintf(line, sizeof line, "BAD R %05u read_ok rename_errno=%d %s", num, errno, strerror(errno));
        show(line);
        return -1;
    }
    note_stall("R", num, read_s);
    snprintf(line, sizeof line, "R %05u read_s=%.3f MBps=%.1f %s",
             num, read_s, (SIZE / 1e6) / read_s, slow ? "good-but-slow" : "good");
    log_line(line);
    return 0;
}

static int read_second(unsigned num, double *secs) {
    char src[512], dst[512], line[256];
    path_for(src, sizeof src, "good but slow", num);
    if (!any_file(src))
        return 1;
    double read_s = 0;
    unsigned long long bad = 0;
    int rc = read_one(src, num, &read_s, &bad);
    *secs = read_s;
    if (rc != 0) {
        path_for(dst, sizeof dst, "failed second read", num);
        rename(src, dst);
        snprintf(line, sizeof line, "BAD SECOND %05u read_s=%.3f bad_bytes=%llu", num, read_s, bad);
        show(line);
        return -1;
    }
    path_for(dst, sizeof dst, "good twice but slow", num);
    if (rename(src, dst) != 0) {
        snprintf(line, sizeof line, "BAD SECOND %05u read_ok rename_errno=%d", num, errno);
        show(line);
        return -1;
    }
    note_stall("SECOND", num, read_s);
    snprintf(line, sizeof line, "SECOND %05u read_s=%.3f MBps=%.1f OK", num, read_s, (SIZE / 1e6) / read_s);
    log_line(line);
    return 0;
}

static void read_untested_ten(unsigned first, double origin, int *read_bad) {
    unsigned nums[10];
    double secs[10];
    int n = 0;
    for (int i = 0; i < 10; i++) {
        unsigned num = first + (unsigned)i;
        if (classify(num) != ST_UNTESTED)
            continue;
        double s = 0;
        int rc = read_first(num, &s);
        if (rc == 1)
            continue;
        nums[n] = num;
        secs[n] = s;
        n++;
        if (rc != 0)
            (*read_bad)++;
    }
    if (n == 0)
        return;
    char line[256];
    batch_line(line, sizeof line, "READ", nums, secs, n, *read_bad, now() - origin);
    show(line);
}

static void usage(void) {
    fprintf(stderr,
            "usage: seagate-media-test-bin VOLUME FIRST GROUPS PER SLOW_SEC DETAIL TIMES ERRORS MAXF\n"
            "Run seagate-media-test.py instead. It documents plan, run, watch, and capture-live.\n");
}

static int parse_u(const char *s, unsigned *out) {
    char *end = NULL;
    unsigned long v;
    if (!s || !*s)
        return -1;
    errno = 0;
    v = strtoul(s, &end, 10);
    if (errno || end == s || *end || v > 0xfffffffful)
        return -1;
    *out = (unsigned)v;
    return 0;
}

static int parse_d(const char *s, double *out) {
    char *end = NULL;
    if (!s || !*s)
        return -1;
    errno = 0;
    *out = strtod(s, &end);
    if (errno || end == s || *end)
        return -1;
    return 0;
}

int main(int argc, char **argv) {
    char line[320];
    unsigned first, groups, per, last;
    if (argc != 10) {
        usage();
        return 2;
    }
    vol = argv[1];
    if (parse_u(argv[2], &first) || parse_u(argv[3], &groups) ||
        parse_u(argv[4], &per) || parse_d(argv[5], &slow_sec) ||
        parse_u(argv[9], &maxf) || !argv[1][0] || !argv[6][0] ||
        !argv[7][0] || !argv[8][0]) {
        usage();
        return 2;
    }
    snprintf(time_path, sizeof time_path, "%s", argv[7]);
    if (first < 1 || groups < 1 || per < 10 || (per % 10u) != 0 || slow_sec <= 0 || maxf < 2) {
        usage();
        return 2;
    }
    if (first > maxf - 1 || groups > (maxf - first) / per) {
        fprintf(stderr, "file range does not fit under MAXF %u\n", maxf);
        return 2;
    }
    setvbuf(stdout, NULL, _IOLBF, 0);
    logf = fopen(argv[6], "a");
    if (!logf) {
        perror(argv[6]);
        return 1;
    }
    errf = fopen(argv[8], "a");
    if (!errf) {
        perror(argv[8]);
        fclose(logf);
        return 1;
    }
    time_of = calloc(maxf, sizeof time_of[0]);
    if (!time_of) {
        fprintf(stderr, "out of memory\n");
        return 1;
    }
    load_times();
    last = first + groups * per - 1;
    snprintf(line, sizeof line, "SIZE %u files %u-%u groups=%u per=%u slow_s=%.1f",
             SIZE, first, last, groups, per, slow_sec);
    show(line);
    double run_t0 = now();
    int run_bad = 0;
    unsigned tens = per / 10u;

    for (unsigned g = 0; g < groups; g++) {
        unsigned base = first + g * per;
        unsigned end = base + per - 1;
        double origin = now();
        int *needs_end = calloc(tens, sizeof *needs_end);
        if (!needs_end) {
            fprintf(stderr, "out of memory\n");
            return 1;
        }
        snprintf(line, sizeof line, "GROUP %u/%u %05u-%05u START", g + 1, groups, base, end);
        show(line);
        int write_bad = 0;
        int read_bad = 0;

        for (unsigned ten = 0; ten < tens; ten++) {
            unsigned ten_first = base + ten * 10u;
            unsigned nums[10];
            double secs[10];
            int nwrite = 0;
            int slow = 0;
            int pending = 0;
            for (int i = 0; i < 10; i++) {
                unsigned num = ten_first + (unsigned)i;
                int st = classify(num);
                if (st == ST_PARTIAL) {
                    write_bad++;
                    snprintf(line, sizeof line, "BAD W %05u partial left in place", num);
                    show(line);
                    continue;
                }
                if (st != ST_MISSING && st != ST_UNTESTED) {
                    if (st == ST_SLOW || (num < maxf && time_of[num] >= slow_sec))
                        slow = 1;
                    continue;
                }
                if (st == ST_MISSING) {
                    char path[512];
                    path_for(path, sizeof path, "untested area", num);
                    double total = 0;
                    int rc = write_one(path, num, &total);
                    int saved = errno;
                    if (rc != 0) {
                        write_bad++;
                        snprintf(line, sizeof line, "BAD W %05u errno=%d %s", num, saved, strerror(saved));
                        show(line);
                        continue;
                    }
                    remember_time(num, total);
                    note_stall("W", num, total);
                    snprintf(line, sizeof line, "W %05u total_s=%.3f MBps=%.1f",
                             num, total, (SIZE / 1e6) / total);
                    log_line(line);
                    nums[nwrite] = num;
                    secs[nwrite] = total;
                    nwrite++;
                    if (total >= slow_sec)
                        slow = 1;
                    pending = 1;
                } else {
                    pending = 1;
                    if (num < maxf && time_of[num] >= slow_sec)
                        slow = 1;
                }
            }
            if (nwrite > 0) {
                batch_line(line, sizeof line, "WRITE", nums, secs, nwrite, write_bad, now() - origin);
                show(line);
            }
            if (pending && slow)
                read_untested_ten(ten_first, origin, &read_bad);
            else if (pending)
                needs_end[ten] = 1;
        }

        snprintf(line, sizeof line, "READ START group=%u", g + 1);
        show(line);
        for (unsigned ten = 0; ten < tens; ten++) {
            if (!needs_end[ten])
                continue;
            read_untested_ten(base + ten * 10u, origin, &read_bad);
        }
        free(needs_end);

        unsigned snums[10];
        double ssecs[10];
        int sn = 0;
        int second_bad = 0;
        int second_n = 0;
        for (unsigned num = base; num <= end; num++) {
            if (classify(num) != ST_SLOW)
                continue;
            double s = 0;
            int rc = read_second(num, &s);
            if (rc == 1)
                continue;
            second_n++;
            if (rc != 0)
                second_bad++;
            snums[sn] = num;
            ssecs[sn] = s;
            sn++;
            if (sn == 10) {
                batch_line(line, sizeof line, "SECOND", snums, ssecs, sn, second_bad, now() - origin);
                show(line);
                sn = 0;
            }
        }
        if (sn > 0) {
            batch_line(line, sizeof line, "SECOND", snums, ssecs, sn, second_bad, now() - origin);
            show(line);
        } else if (second_n == 0) {
            snprintf(line, sizeof line, "SECOND NONE group=%u", g + 1);
            show(line);
        }
        run_bad += write_bad + read_bad + second_bad;
        snprintf(line, sizeof line,
                 "GROUP %u/%u DONE elapsed_s=%.0f write_bad=%d read_bad=%d second_bad=%d",
                 g + 1, groups, now() - origin, write_bad, read_bad, second_bad);
        show(line);
    }

    snprintf(line, sizeof line, "ALL DONE files=%u elapsed_s=%.0f bad=%d",
             groups * per, now() - run_t0, run_bad);
    show(line);
    fclose(logf);
    if (errf)
        fclose(errf);
    free(time_of);
    return run_bad ? 1 : 0;
}
