/* A compiled cart's writable files in a folder (moy_files.h). */

#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#ifdef _WIN32
#include <direct.h>
#include <io.h>
#else
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

#include "moy_files.h"

#define PART "~part"
#define DONE "~done"
/* A key is at most three characters a byte; a folder path, whatever the
 * host's own is. */
#define KEY_MAX (MOY_WASM_PATH_MAX * 3 + 1)
#define PATH_MAX_ 1024
/* How deep `list` walks the cart's folder. */
#define DEPTH_MAX 16

struct moy_files {
    char *dir;                  /* NULL: nothing is kept */
    char *cart;
    int made;                   /* `dir` exists */
    int stale;                  /* the listing no longer says what is there */
    char **names;               /* the listing: sorted, each path once */
    size_t n, cap;
};

/* -- the key ---------------------------------------------------------------- */

static int kept_byte(unsigned char c, size_t i, size_t len)
{
    if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-')
        return 1;
    return c == '.' && i > 0 && i + 1 < len;
}

/* Windows keeps these names for devices whatever follows a dot, so a key
 * that would be one has its first byte written out. */
static int device_name(const char *key)
{
    static const char *const NAMES[] = { "con", "prn", "aux", "nul" };
    size_t stem = strcspn(key, "."), i;
    for (i = 0; i < sizeof NAMES / sizeof NAMES[0]; i++)
        if (stem == 3 && !strncmp(key, NAMES[i], 3)) return 1;
    return stem == 4 && (!strncmp(key, "com", 3) || !strncmp(key, "lpt", 3))
        && key[3] >= '1' && key[3] <= '9';
}

static int encode(const char *path, char *out, size_t n, int first_out)
{
    static const char HEX[] = "0123456789abcdef";
    size_t len = strlen(path), i, o = 0;
    for (i = 0; i < len; i++) {
        unsigned char c = (unsigned char)path[i];
        if (kept_byte(c, i, len) && !(i == 0 && first_out)) {
            if (o + 1 >= n) return -1;
            out[o++] = (char)c;
        } else {
            if (o + 3 >= n) return -1;
            out[o++] = '%';
            out[o++] = HEX[c >> 4];
            out[o++] = HEX[c & 15u];
        }
    }
    if (o >= n) return -1;
    out[o] = 0;
    return (int)o;
}

int moy_files_key(const char *path, char *out, size_t n)
{
    int r = encode(path, out, n, 0);
    if (r > 0 && device_name(out)) r = encode(path, out, n, 1);
    return r;
}

static int hex(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

/* A key back to its path: 0, or -1 for a name that is not a key. */
static int decode(const char *key, char *out, size_t n)
{
    size_t o = 0;
    for (; *key; key++) {
        int c = (unsigned char)*key;
        if (c == '~') return -1;
        if (c == '%') {
            int hi = hex(key[1]), lo = hi < 0 ? -1 : hex(key[2]);
            if (lo < 0) return -1;
            c = hi * 16 + lo;
            key += 2;
        }
        if (o + 1 >= n) return -1;
        out[o++] = (char)c;
    }
    out[o] = 0;
    return o ? 0 : -1;
}

/* -- the folder ------------------------------------------------------------- */

static char *copy_str(const char *s)
{
    size_t n = strlen(s) + 1;
    char *d = (char *)malloc(n);
    if (d) memcpy(d, s, n);
    return d;
}

static int make_dir(const char *p)
{
#ifdef _WIN32
    return _mkdir(p);
#else
    return mkdir(p, 0777);
#endif
}

/* `dir` and every folder above it. */
static int make_dirs(const char *dir)
{
    char p[PATH_MAX_];
    size_t i, n = strlen(dir);
    DIR *d;
    if (n >= sizeof p) return -1;
    memcpy(p, dir, n + 1);
    for (i = 1; i <= n; i++) {
        if (p[i] != '/' && p[i] != '\\' && p[i] != 0) continue;
        p[i] = 0;
        make_dir(p);
        p[i] = dir[i];
    }
    d = opendir(dir);
    if (!d) return -1;
    closedir(d);
    return 0;
}

static int is_dir(const char *p)
{
    DIR *d = opendir(p);
    if (!d) return 0;
    closedir(d);
    return 1;
}

static int join(char *out, size_t n, const char *a, const char *b, const char *c)
{
    int r = snprintf(out, n, "%s/%s%s", a, b, c ? c : "");
    return r < 0 || (size_t)r >= n ? -1 : 0;
}

/* `p` replaced by `q`'s file. Windows will not rename over a file. */
static int replace(const char *q, const char *p)
{
#ifdef _WIN32
    remove(p);
#endif
    return rename(q, p);
}

/* What a crash left in the folder: a "~done" is whole and replaces its file,
 * a "~part" is not and goes. */
static void recover(moy_files *f)
{
    DIR *d = opendir(f->dir);
    struct dirent *e;
    char from[PATH_MAX_], to[PATH_MAX_];
    if (!d) return;
    f->made = 1;
    while ((e = readdir(d)) != NULL) {
        size_t n = strlen(e->d_name);
        if (n > 5 && !strcmp(e->d_name + n - 5, DONE)) {
            if (join(from, sizeof from, f->dir, e->d_name, NULL)) continue;
            memcpy(to, from, strlen(from) - 5);
            to[strlen(from) - 5] = 0;
            replace(from, to);
        } else if (n > 5 && !strcmp(e->d_name + n - 5, PART)) {
            if (!join(from, sizeof from, f->dir, e->d_name, NULL)) remove(from);
        }
    }
    closedir(d);
}

moy_files *moy_files_open(const char *dir, const char *cart)
{
    moy_files *f = (moy_files *)calloc(1, sizeof *f);
    if (!f) return NULL;
    f->cart = copy_str(cart ? cart : ".");
    f->dir = dir ? copy_str(dir) : NULL;
    f->stale = 1;
    if (!f->cart || (dir && !f->dir)) {
        moy_files_close(f);
        return NULL;
    }
    if (f->dir) recover(f);
    return f;
}

static void forget(moy_files *f)
{
    size_t i;
    for (i = 0; i < f->n; i++) free(f->names[i]);
    f->n = 0;
    f->stale = 1;
}

void moy_files_close(moy_files *f)
{
    if (!f) return;
    forget(f);
    free(f->names);
    free(f->dir);
    free(f->cart);
    free(f);
}

/* -- the binding's four ------------------------------------------------------ */

static int key_path(const moy_files *f, const char *path, const char *suffix,
                    char *out, size_t n)
{
    char key[KEY_MAX];
    if (!f->dir || moy_files_key(path, key, sizeof key) < 0) return -1;
    return join(out, n, f->dir, key, suffix);
}

static int32_t f_written(void *user, const char *path, uint32_t offset,
                         uint8_t *dst, uint32_t len)
{
    moy_files *f = (moy_files *)user;
    char p[PATH_MAX_];
    FILE *fp;
    long size;
    int32_t got = 0;
    if (key_path(f, path, NULL, p, sizeof p)) return -1;
    fp = fopen(p, "rb");
    if (!fp) return -1;
    if (fseek(fp, 0, SEEK_END) == 0 && (size = ftell(fp)) >= 0
        && (unsigned long)size > offset) {
        uint32_t left = (uint32_t)((unsigned long)size - offset);
        if (len == 0) got = (int32_t)left;
        else if (fseek(fp, (long)offset, SEEK_SET) == 0)
            got = (int32_t)fread(dst, 1, len < left ? len : left, fp);
    }
    fclose(fp);
    return got;
}

static int32_t no_room_or_failed(int e)
{
#ifdef EDQUOT
    if (e == EDQUOT) return MOY_WASM_NO_ROOM;
#endif
    return e == ENOSPC ? MOY_WASM_NO_ROOM : MOY_WASM_FAILED;
}

/* The bytes on the medium before the file is closed. */
static int sync_file(FILE *fp)
{
    if (fflush(fp) != 0) return -1;
#ifdef _WIN32
    return _commit(_fileno(fp));
#else
    return fsync(fileno(fp));
#endif
}

/* The folder's entries on the medium, so a rename survives a power loss. */
static void sync_dir(const char *dir)
{
#ifdef _WIN32
    (void)dir;
#else
    int fd = open(dir, O_RDONLY);
    if (fd < 0) return;
    fsync(fd);
    close(fd);
#endif
}

static int32_t f_write(void *user, const char *path, const uint8_t *data, uint32_t len)
{
    moy_files *f = (moy_files *)user;
    char part[PATH_MAX_], done[PATH_MAX_], target[PATH_MAX_];
    FILE *fp;
    int e = 0;
    if (!f->dir || key_path(f, path, PART, part, sizeof part)
        || key_path(f, path, DONE, done, sizeof done)
        || key_path(f, path, NULL, target, sizeof target))
        return MOY_WASM_FAILED;
    errno = 0;
    if (!f->made) {
        if (make_dirs(f->dir)) return no_room_or_failed(errno);
        f->made = 1;
    }
    fp = fopen(part, "wb");
    if (!fp) return no_room_or_failed(errno);
    if ((len && fwrite(data, 1, len, fp) != len) || sync_file(fp)) e = errno ? errno : EIO;
    if (fclose(fp) != 0 && !e) e = errno ? errno : EIO;
    if (e) {
        remove(part);
        return no_room_or_failed(e);
    }
    remove(done);
    if (rename(part, done) != 0) {
        remove(part);
        return MOY_WASM_FAILED;
    }
    /* From here a crash leaves "~done", which the next open puts in place. */
    if (replace(done, target) != 0) return MOY_WASM_FAILED;
    sync_dir(f->dir);
    f->stale = 1;
    return 0;
}

static int32_t f_erase(void *user, const char *path)
{
    moy_files *f = (moy_files *)user;
    char p[PATH_MAX_];
    if (key_path(f, path, NULL, p, sizeof p) || remove(p) != 0) return -1;
    sync_dir(f->dir);
    f->stale = 1;
    return 0;
}

/* -- list --------------------------------------------------------------------- */

static int add(moy_files *f, const char *name)
{
    char *d;
    if (f->n == f->cap) {
        size_t cap = f->cap ? f->cap * 2 : 64;
        char **grown = (char **)realloc(f->names, cap * sizeof *grown);
        if (!grown) return -1;
        f->names = grown;
        f->cap = cap;
    }
    d = copy_str(name);
    if (!d) return -1;
    f->names[f->n++] = d;
    return 0;
}

/* Every file under `dir`, named from the cart's root by `rel`. */
static void walk(moy_files *f, const char *dir, const char *rel, int depth)
{
    DIR *d = opendir(dir);
    struct dirent *e;
    char p[PATH_MAX_], r[PATH_MAX_];
    if (!d) return;
    while ((e = readdir(d)) != NULL) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        if (join(p, sizeof p, dir, e->d_name, NULL)) continue;
        if (rel[0]) {
            if (join(r, sizeof r, rel, e->d_name, NULL)) continue;
        } else if (snprintf(r, sizeof r, "%s", e->d_name) >= (int)sizeof r) {
            continue;
        }
        if (is_dir(p)) {
            if (depth < DEPTH_MAX) walk(f, p, r, depth + 1);
        } else if (strlen(r) <= MOY_WASM_NAME_MAX) {
            add(f, r);
        }
    }
    closedir(d);
}

static int by_bytes(const void *a, const void *b)
{
    return strcmp(*(char *const *)a, *(char *const *)b);
}

static void build(moy_files *f)
{
    size_t i, o;
    forget(f);
    walk(f, f->cart, "", 0);
    if (f->dir) {
        DIR *d = opendir(f->dir);
        struct dirent *e;
        char path[MOY_WASM_PATH_MAX + 1];
        while (d && (e = readdir(d)) != NULL)
            if (!decode(e->d_name, path, sizeof path)) add(f, path);
        if (d) closedir(d);
    }
    if (f->n) qsort(f->names, f->n, sizeof *f->names, by_bytes);
    for (i = o = 0; i < f->n; i++) {
        if (o && !strcmp(f->names[o - 1], f->names[i])) {
            free(f->names[i]);
            continue;
        }
        f->names[o++] = f->names[i];
    }
    f->n = o;
    f->stale = 0;
}

static int32_t f_list(void *user, const char *prefix, uint32_t index,
                      uint8_t *dst, uint32_t len)
{
    moy_files *f = (moy_files *)user;
    size_t lo = 0, hi, plen = strlen(prefix), n;
    const char *name;
    if (f->stale) build(f);
    hi = f->n;
    while (lo < hi) {                        /* the first name not below prefix */
        size_t mid = lo + (hi - lo) / 2;
        if (strcmp(f->names[mid], prefix) < 0) lo = mid + 1;
        else hi = mid;
    }
    if (lo + index >= f->n) return -1;
    name = f->names[lo + index];
    if (strncmp(name, prefix, plen) != 0) return -1;
    n = strlen(name);
    memcpy(dst, name, n < len ? n : len);
    return (int32_t)n;
}

void moy_files_bind(moy_files *f, moy_wasm *w)
{
    w->written = f_written;
    w->write = f_write;
    w->erase = f_erase;
    w->list = f_list;
    w->files_user = f;
}
