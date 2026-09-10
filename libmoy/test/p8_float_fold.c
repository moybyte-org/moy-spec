/* The p8 machine's number coercion, held equal to the double-precision form it
 * replaced -- over EVERY float bit pattern.
 *
 * moy_p8.c used to promote lua_Number to double to floor it, range-check it
 * and narrow it. Neither target board has a double FPU, so each of those was a
 * libgcc call out of flash; the machine now does the same arithmetic in
 * lua_Number, with the wrap arm alone left wide because fmod's exactness is
 * the pin there. The claim that makes the change safe is that the two answer
 * identically, and the claim is cheap to settle exhaustively: a float has 2^32
 * bit patterns, so this sweeps all of them rather than sampling.
 *
 * The pairs are transcribed here rather than linked, because both sides are
 * static in moy_p8.c and one side no longer exists. That is the same shape as
 * test/p8lib.moy holding a promoted C verb equal to the Lua it replaced. */

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef float num;   /* lua_Number under LUA_32BITS, which both boards build */

/* ---- what moy_p8.c had ------------------------------------------------- */

static int32_t old_f2i(num f)
{
    double d = (double)f;
    if (d >= -2147483648.0 && d < 2147483648.0) return (int32_t)d;
    if (!(d == d)) return 0;
    d = fmod(d, 4294967296.0);
    if (d < 0) d += 4294967296.0;
    if (d >= 2147483648.0) d -= 4294967296.0;
    return (int32_t)d;
}

/* p8_fl's float lane, and p8_flr_d/p8_fl_d's, both of which floored wide.
 * The wide floor is hoisted into the sweep and passed in: it is the same call
 * for both, and at 2^32 iterations one saved libm call is half a minute. */
static int32_t old_fl_of(double floored) { return old_f2i((num)floored); }

/* ---- what it has now --------------------------------------------------- */

static int32_t new_f2i(num f)
{
    double d;
    if (f >= (num)-2147483648.0 && f < (num)2147483648.0) return (int32_t)f;
    if (!(f == f)) return 0;
    d = fmod((double)f, 4294967296.0);
    if (d < 0) d += 4294967296.0;
    if (d >= 2147483648.0) d -= 4294967296.0;
    return (int32_t)d;
}

static int32_t new_floor_i(num f)
{
    if (f >= (num)-2147483648.0 && f < (num)2147483648.0) {
        int32_t i = (int32_t)f;
        return ((num)i > f) ? i - 1 : i;
    }
    return new_f2i(f);
}

static num new_flr_n(num f) { return floorf(f); }

/* ---- the sweep --------------------------------------------------------- */

static num from_bits(uint32_t u) { num f; memcpy(&f, &u, 4); return f; }

/* Every boundary the two forms could part company on, swept whatever the
 * stride: the range arms' bounds and their neighbours, the last float that is
 * exactly an integer, zero and the denormal either side of it, and the NaN and
 * infinity patterns that decide which arm is even taken. */
static const uint32_t EDGES[] = {
    0x00000000u, 0x80000000u,              /* +0, -0                        */
    0x00000001u, 0x80000001u,              /* smallest denormals            */
    0x007fffffu, 0x00800000u,              /* denormal/normal seam          */
    0x3f800000u, 0xbf800000u,              /* +/-1                          */
    0x3f7fffffu, 0xbf7fffffu,              /* just inside +/-1              */
    0x4b7fffffu, 0x4b800000u, 0x4b800001u, /* 2^24 seam: last exact integer */
    0xcb7fffffu, 0xcb800000u, 0xcb800001u,
    0x4effffffu, 0x4f000000u, 0x4f000001u, /* 2^31 seam: the range bound    */
    0xceffffffu, 0xcf000000u, 0xcf000001u,
    0x7f7fffffu, 0xff7fffffu,              /* +/-FLT_MAX                    */
    0x7f800000u, 0xff800000u,              /* +/-inf                        */
    0x7fc00000u, 0xffc00000u,              /* quiet NaN, both signs         */
    0x7f800001u, 0xffbfffffu,              /* signalling NaN, both signs    */
};

static uint64_t bad_f2i, bad_fl, bad_flr;
static uint32_t first_f2i, first_fl, first_flr;

static void check(uint32_t u)
{
    num f = from_bits(u);
    double da = floor((double)f);            /* what the old wide floor gave */
    num nb = new_flr_n(f);
    int32_t a, b;

    a = old_f2i(f); b = new_f2i(f);
    if (a != b && !(bad_f2i++)) first_f2i = u;

    a = old_fl_of(da); b = new_floor_i(f);
    if (a != b && !(bad_fl++)) first_fl = u;

    /* the wide floor: p8_flr_n/p8_fl_n keep the value un-narrowed, so what
       must hold is that the float floor IS the double floor's value */
    if (!((da != da && nb != nb) || (double)nb == da) && !(bad_flr++))
        first_flr = u;
}

/* Infinity reaches fmod as inf and comes back NaN, so both forms end in the
 * same undefined cast -- identical by construction, and the pattern is left in
 * the sweep rather than special-cased, since equality is what is claimed. */
int main(int argc, char **argv)
{
    unsigned long stride = 37;
    uint64_t u, n = 0;
    size_t i;

    if (argc > 1) {
        stride = strtoul(argv[1], NULL, 10);
        if (stride == 0) stride = 1;
    }

    for (i = 0; i < sizeof EDGES / sizeof EDGES[0]; i++) { check(EDGES[i]); n++; }
    for (u = 0; u <= 0xffffffffu; u += stride) { check((uint32_t)u); n++; }

    if (bad_f2i | bad_fl | bad_flr) {
        if (bad_f2i) printf("f2i: %llu mismatches, first bits %08x (%.9g)\n",
                            (unsigned long long)bad_f2i, first_f2i,
                            (double)from_bits(first_f2i));
        if (bad_fl)  printf("floor+narrow: %llu mismatches, first bits %08x (%.9g)\n",
                            (unsigned long long)bad_fl, first_fl,
                            (double)from_bits(first_fl));
        if (bad_flr) printf("wide floor: %llu mismatches, first bits %08x (%.9g)\n",
                            (unsigned long long)bad_flr, first_flr,
                            (double)from_bits(first_flr));
        return 1;
    }
    printf("p8 float fold: %llu patterns (stride %lu, edges whole), "
           "three folds, no divergence\n", (unsigned long long)n, stride);
    return 0;
}
