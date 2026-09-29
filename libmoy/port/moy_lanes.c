/* Lanes for libmoy's wasm binding over POSIX threads (moy_lanes.h). */

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

#include "moy_lanes.h"

typedef struct {
    pthread_t thread;
    int up;
    /* guarded by `lock`: work handed over and not yet started, work running,
     * and the call to end */
    int handed, running, quit;
    void (*work)(void *);
    void *job;
} lane;

struct moy_lanes {
    pthread_mutex_t lock;
    pthread_cond_t wake, idle;
    int n;
    long started;
    lane lane[MOY_WASM_LANES + 1];          /* [1..n] */
};

typedef struct {
    moy_lanes *l;
    int k;
} start;

static void *run(void *arg)
{
    start *s = (start *)arg;
    moy_lanes *l = s->l;
    lane *me = &l->lane[s->k];
    free(s);
    wasm_runtime_init_thread_env();
    pthread_mutex_lock(&l->lock);
    for (;;) {
        while (!me->handed && !me->quit) pthread_cond_wait(&l->wake, &l->lock);
        if (me->quit) break;
        me->handed = 0;
        me->running = 1;
        l->started++;
        pthread_mutex_unlock(&l->lock);
        me->work(me->job);
        pthread_mutex_lock(&l->lock);
        me->running = 0;
        pthread_cond_broadcast(&l->idle);
    }
    pthread_mutex_unlock(&l->lock);
    wasm_runtime_destroy_thread_env();
    return NULL;
}

int moy_lanes_cores(void)
{
#ifdef _WIN32
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    return si.dwNumberOfProcessors < 1 ? 1 : (int)si.dwNumberOfProcessors;
#else
    long n = sysconf(_SC_NPROCESSORS_ONLN);
    return n < 1 ? 1 : (int)n;
#endif
}

moy_lanes *moy_lanes_open(int n)
{
    moy_lanes *l;
    int k;
    if (n < 1) return NULL;
    if (n > MOY_WASM_LANES) n = MOY_WASM_LANES;
    l = (moy_lanes *)calloc(1, sizeof *l);
    if (!l) return NULL;
    pthread_mutex_init(&l->lock, NULL);
    pthread_cond_init(&l->wake, NULL);
    pthread_cond_init(&l->idle, NULL);
    for (k = 1; k <= n; k++) {
        start *s = (start *)malloc(sizeof *s);
        if (!s) break;
        s->l = l;
        s->k = k;
        if (pthread_create(&l->lane[k].thread, NULL, run, s) != 0) {
            free(s);
            break;
        }
        l->lane[k].up = 1;
        l->n = k;
    }
    if (!l->n) {
        moy_lanes_close(l);
        return NULL;
    }
    return l;
}

static int go(void *user, int k, void (*work)(void *), void *job)
{
    moy_lanes *l = (moy_lanes *)user;
    if (k < 1 || k > l->n) return 1;
    pthread_mutex_lock(&l->lock);
    l->lane[k].work = work;
    l->lane[k].job = job;
    l->lane[k].handed = 1;
    pthread_cond_broadcast(&l->wake);
    pthread_mutex_unlock(&l->lock);
    return 0;
}

/* Work the lane has not started is taken back rather than waited for: the
 * binding waits only once every item is taken, so the lane would find none. */
static void wait_for(void *user, int k)
{
    moy_lanes *l = (moy_lanes *)user;
    if (k < 1 || k > l->n) return;
    pthread_mutex_lock(&l->lock);
    l->lane[k].handed = 0;
    while (l->lane[k].running) pthread_cond_wait(&l->idle, &l->lock);
    pthread_mutex_unlock(&l->lock);
}

void moy_lanes_bind(moy_lanes *l, moy_wasm *w)
{
    w->lanes = l ? l->n : 0;
    w->lane_go = l ? go : NULL;
    w->lane_wait = l ? wait_for : NULL;
    w->lane_user = l;
}

long moy_lanes_started(const moy_lanes *l)
{
    return l ? l->started : 0;
}

void moy_lanes_close(moy_lanes *l)
{
    int k;
    if (!l) return;
    pthread_mutex_lock(&l->lock);
    for (k = 1; k <= MOY_WASM_LANES; k++) l->lane[k].quit = 1;
    pthread_cond_broadcast(&l->wake);
    pthread_mutex_unlock(&l->lock);
    for (k = 1; k <= MOY_WASM_LANES; k++)
        if (l->lane[k].up) pthread_join(l->lane[k].thread, NULL);
    pthread_cond_destroy(&l->idle);
    pthread_cond_destroy(&l->wake);
    pthread_mutex_destroy(&l->lock);
    free(l);
}
