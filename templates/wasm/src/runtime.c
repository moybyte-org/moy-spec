/* The C library's edges a compiled cart owns: the heap, and the few calls the
 * C library makes to an operating system. A cart has no operating system --
 * its only imports are the console's, from module "moy" (SPEC.md 16.2) -- so
 * this file answers those calls itself, and malloc, printf-to-a-string and
 * the rest of the C library work with nothing imported.
 *
 * You should not need to edit this file.
 *
 * THE HEAP is the linear memory above the stack and the static data, from
 * __heap_base to __heap_end, which the linker places: the end of the memory
 * manifest.json declares, which never grows (SPEC.md 16.7). Asking the memory
 * its size instead would tell the ahead-of-time compilers the memory can
 * grow, and they would reload its base after every call.
 *
 * Best fit over an address-ordered free list, neighbours merged on free, every
 * block 16-aligned with a 16-byte header, and two-ended: a block of LARGE
 * bytes or more comes from the top of the heap down, a smaller one from the
 * bottom up, so big long-lived buffers and small churn do not fragment each
 * other. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>

extern unsigned char __heap_base;
extern unsigned char __heap_end;

typedef struct Block {
    size_t size; /* the whole block, header included */
    size_t used;
    struct Block *next; /* free blocks only */
    size_t pad;
} Block;

#define HEADER sizeof(Block)
#define ALIGN 16
#define LARGE 4096

static Block *free_list;
/* The small blocks' end and the large blocks' start: [low, high) is unused. */
static uintptr_t heap_start, low, high, heap_end;

static size_t round_up(size_t n) { return (n + ALIGN - 1) & ~(size_t)(ALIGN - 1); }

static void start(void)
{
    if (heap_end) return;
    heap_start = low = round_up((uintptr_t)&__heap_base);
    heap_end = high = (uintptr_t)&__heap_end & ~(uintptr_t)(ALIGN - 1);
}

static Block *header(void *p) { return (Block *)((unsigned char *)p - HEADER); }

static void unlink_block(Block *b)
{
    Block **at = &free_list;
    while (*at != b) at = &(*at)->next;
    *at = b->next;
}

static void insert(Block *b)
{
    Block **at = &free_list;
    b->used = 0;
    while (*at && *at < b) at = &(*at)->next;
    b->next = *at;
    *at = b;
    if (b->next && (uintptr_t)b + b->size == (uintptr_t)b->next) {
        b->size += b->next->size;
        b->next = b->next->next;
    }
    if (at != &free_list) {
        Block *prev = (Block *)((unsigned char *)at - offsetof(Block, next));
        if ((uintptr_t)prev + prev->size == (uintptr_t)b) {
            prev->size += b->size;
            prev->next = b->next;
            b = prev;
        }
    }
    /* A free block touching the unused middle goes back into it. */
    if ((uintptr_t)b + b->size == low) {
        unlink_block(b);
        low = (uintptr_t)b;
    } else if ((uintptr_t)b == high) {
        unlink_block(b);
        high += b->size;
    }
}

void *malloc(size_t n)
{
    size_t need;
    int large;
    Block **best = NULL, **at, *b;
    start();
    if (n > heap_end) return NULL;
    need = round_up(n ? n : 1) + HEADER;
    large = need >= LARGE;
    for (at = &free_list; *at; at = &(*at)->next) {
        if ((*at)->size < need || (best && (*best)->size <= (*at)->size)) continue;
        best = at;
        if ((*at)->size == need) break;
    }
    if (best) {
        b = *best;
        if (b->size - need < HEADER + ALIGN) {
            *best = b->next;
        } else if (large) {
            b->size -= need;
            b = (Block *)((unsigned char *)b + b->size);
            b->size = need;
        } else {
            Block *rest = (Block *)((unsigned char *)b + need);
            rest->size = b->size - need;
            rest->used = 0;
            rest->next = b->next;
            *best = rest;
            b->size = need;
        }
    } else {
        if (high - low < need) return NULL;
        if (large) {
            high -= need;
            b = (Block *)high;
        } else {
            b = (Block *)low;
            low += need;
        }
        b->size = need;
    }
    b->used = 1;
    return (unsigned char *)b + HEADER;
}

void free(void *p)
{
    if (p) insert(header(p));
}

void *calloc(size_t n, size_t size)
{
    void *p;
    if (size && n > (size_t)-1 / size) return NULL;
    p = malloc(n * size);
    if (p) memset(p, 0, n * size);
    return p;
}

void *realloc(void *p, size_t n)
{
    size_t have;
    void *q;
    if (!p) return malloc(n);
    if (!n) {
        free(p);
        return NULL;
    }
    have = header(p)->size - HEADER;
    if (have >= n) return p;
    q = malloc(n);
    if (q) {
        memcpy(q, p, have);
        free(p);
    }
    return q;
}

void *aligned_alloc(size_t align, size_t n) { return align <= ALIGN ? malloc(n) : NULL; }

int posix_memalign(void **out, size_t align, size_t n)
{
    void *p = aligned_alloc(align, n);
    if (!p) return 12; /* ENOMEM */
    *out = p;
    return 0;
}

/* The C library's own routines allocate through these names. */
void *__libc_malloc(size_t n) { return malloc(n); }
void *__libc_calloc(size_t n, size_t size) { return calloc(n, size); }
void __libc_free(void *p) { free(p); }
size_t malloc_usable_size(void *p) { return p ? header(p)->size - HEADER : 0; }

/* The operating-system calls the C library's stdio makes. A cart has no
 * terminal: a write succeeds and goes nowhere, and the streams never seek or
 * close. Defining them here is what keeps them from being imported. */
typedef struct {
    uint32_t buf, len;
} Iovec;

#define WASI_EBADF 8

int32_t __imported_wasi_snapshot_preview1_fd_write(int32_t fd, int32_t iovs, int32_t n,
                                                    int32_t nwritten)
{
    const Iovec *v = (const Iovec *)(uintptr_t)iovs;
    uint32_t total = 0;
    int32_t i;
    (void)fd;
    for (i = 0; i < n; i++) total += v[i].len;
    *(uint32_t *)(uintptr_t)nwritten = total;
    return 0;
}

int32_t __imported_wasi_snapshot_preview1_fd_seek(int32_t fd, int64_t offset, int32_t whence,
                                                   int32_t out)
{
    (void)fd, (void)offset, (void)whence, (void)out;
    return WASI_EBADF;
}

int32_t __imported_wasi_snapshot_preview1_fd_close(int32_t fd)
{
    (void)fd;
    return WASI_EBADF;
}

int32_t __imported_wasi_snapshot_preview1_fd_fdstat_get(int32_t fd, int32_t out)
{
    (void)fd, (void)out;
    return WASI_EBADF;
}
