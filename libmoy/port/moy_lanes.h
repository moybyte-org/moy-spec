/* Lanes for libmoy's wasm binding over POSIX threads: what a desktop host
 * hands moy_wasm's `lanes`, `lane_go` and `lane_wait` (include/moy_wasm.h),
 * so a compiled cart's par items run on the machine's other cores.
 *
 * Built only beside the binding over WAMR (MOY_WASM): a lane's thread is one
 * WAMR must be able to run on, so it sets up WAMR's per-thread state when it
 * starts and tears it down when it ends.
 *
 *   moy_lanes *lanes = moy_lanes_open(moy_lanes_cores() - 1);
 *   moy_lanes_bind(lanes, &w);                 // before moy_wasm_open
 *   ...the cart runs...
 *   moy_wasm_close(&w);                        // frees the lanes' instances
 *   moy_lanes_close(lanes);                    // then the threads
 */

#ifndef MOY_LANES_H_INCLUDED
#define MOY_LANES_H_INCLUDED

#include "moy_wasm.h"

typedef struct moy_lanes moy_lanes;

/* The cores this machine has, at least 1. */
int moy_lanes_cores(void);

/* `n` lane threads, at most MOY_WASM_LANES, started now and idle until the
 * binding hands them work. NULL when n < 1 or none could start. */
moy_lanes *moy_lanes_open(int n);

/* Point the binding's lane fields at these lanes. */
void moy_lanes_bind(moy_lanes *l, moy_wasm *w);

/* How many times a lane started work since the lanes opened (work taken back
 * before it started does not count). */
long moy_lanes_started(const moy_lanes *l);

/* Join the threads and free them. Safe on NULL. Call it after moy_wasm_close. */
void moy_lanes_close(moy_lanes *l);

#endif
