/* A compiled cart's writable files in a folder (SPEC.md 16.12): what a host
 * with a filesystem hands moy_wasm's `written`, `write`, `erase` and `list`
 * (include/moy_wasm.h). The desktop player keeps a cart's files with it, and
 * the WAMR harness when it plays a conformance scene.
 *
 *   moy_files *files = moy_files_open(dir, cart);   // dir NULL: none kept
 *   moy_files_bind(files, &w);                      // before the cart runs
 *   ...the cart runs...
 *   moy_files_close(files);
 *
 * ONE FOLDER PER CART, FLAT. A written path is one file in `dir`, named by its
 * key (moy_files_key), so a path's slashes make no folders and a path cannot
 * be a file and a folder at once. The key keeps a-z, 0-9, '_', '-' and an
 * inner '.', and writes every other byte as '%' and two lowercase hex digits:
 * a key is lowercase and portable, so a case-insensitive filesystem still
 * keeps "Save" and "save" apart, and every key decodes back to its path for
 * `list`. At 64 bytes a path's key is at most 192 characters.
 *
 * A WRITE IS ATOMIC. It goes to "<key>~part", which becomes "<key>~done" once
 * it is whole and synced, and then replaces "<key>". A key never holds '~',
 * so neither name is a written file. Opening the folder finishes what a crash
 * left: a "~done" replaces its file, a "~part" goes.
 *
 * `list` is the cart's folder, every file at any depth, and the written files
 * together, sorted and each path once. The listing is built on the first
 * `list` and kept until a write or an erase changes the files.
 */

#ifndef MOY_FILES_H_INCLUDED
#define MOY_FILES_H_INCLUDED

#include <stddef.h>

#include "moy_wasm.h"

typedef struct moy_files moy_files;

/* The written files kept in `dir`, which is made the first time a file is
 * written, and the files of the cart in folder `cart`, which `list` walks.
 * With `dir` NULL nothing is kept: every write fails, and `list` answers the
 * cart's folder alone. NULL when out of memory. */
moy_files *moy_files_open(const char *dir, const char *cart);

/* Point the binding's written-file fields at these files. `writable` is left
 * as the host set it. */
void moy_files_bind(moy_files *f, moy_wasm *w);

/* Free the store. Safe on NULL. */
void moy_files_close(moy_files *f);

/* The file name `path` is kept under, into `out`: its length, or -1 when it
 * does not fit `n` bytes with its NUL. */
int moy_files_key(const char *path, char *out, size_t n);

#endif
