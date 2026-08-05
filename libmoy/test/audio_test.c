/* audio_test -- the SPEC.md 8 semantics, asserted without a speaker.
 *
 * 8.3 exempts audio from bit-identical conformance, so there are no PCM
 * goldens to replay. What CAN be pinned is everything musical the section
 * promises: a pitch is its frequency (counted as zero crossings), a fade
 * ends silent, music claims channels from the top, effects round-robin what
 * music leaves free, and every stop verb actually stops. Those are the
 * semantics imported carts depend on, and each one here failed at least
 * once while this file was being written. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy_audio.h"

#define RATE 44100

static int failures;

static void check(int cond, const char *what)
{
    if (!cond) {
        fprintf(stderr, "FAIL: %s\n", what);
        failures++;
    }
}

static int crossings(const int16_t *buf, int n)
{
    int i, c = 0;
    for (i = 1; i < n; i++)
        if ((buf[i - 1] < 0) != (buf[i] < 0)) c++;
    return c;
}

static float rms(const int16_t *buf, int n)
{
    double acc = 0;
    int i;
    for (i = 0; i < n; i++) acc += (double)buf[i] * buf[i];
    return (float)(acc / n);
}

static int16_t buf[RATE * 2];

int main(void)
{
    moy_bank bank;
    moy_audio a;

    /* -- parsing ---------------------------------------------------- */
    check(moy_bank_parse(&bank, NULL) == 0, "NULL sounds.json is a silent cart");
    check(moy_bank_parse(&bank, "  ") == 0, "empty text is a silent cart");
    check(moy_bank_parse(&bank, "{\"sfx\":[{\"steps\":[[57,0") != 0,
          "truncated JSON is refused");
    check(moy_bank_parse(&bank, "not json") != 0, "junk is refused");

    check(moy_bank_parse(&bank,
        "{\"sfx\":[{\"speed\":1,\"steps\":[[57,0,7]]},"
        "         {\"speed\":8,\"loop\":true,\"steps\":[[30,1,6],[32,1,6]]}],"
        " \"music\":[{\"speed\":4,\"pattern\":[[0,1]]},"
        "            {\"pattern\":[0],\"row_secs\":[0]}],"
        " \"future_field\":{\"ignored\":[1,2,{\"deep\":true}]}}") == 0,
        "the reference bank parses");
    check(bank.nsfx == 2 && bank.nmusic == 2, "counts");
    check(bank.sfx[0].nsteps == 1 && bank.sfx[0].speed == 1.0f, "sfx 0 shape");
    check(bank.sfx[1].loop == 1, "sfx 1 loops");
    check(bank.music[0].width == 2, "track 0 claims two channels");
    check(bank.music[1].has_row_secs && bank.music[1].row_secs[0] == 0.0f,
          "row_secs parsed");

    /* -- pitch: A4 is 440 Hz --------------------------------------- */
    moy_audio_init(&a, &bank, RATE);
    moy_audio_sfx(&a, 0, -1);           /* [57,0,7]: A4, square, 1 second */
    moy_audio_render(&a, buf, RATE);
    {
        /* A 440 Hz square crosses zero 880 times a second. */
        int c = crossings(buf, RATE);
        check(c > 860 && c < 900, "A4 square crosses ~880 times/s");
    }
    check(a.v[0].owner == 0, "a non-looping sfx ends");

    /* -- fade out ends silent (eff 5) ------------------------------- */
    check(moy_bank_parse(&bank,
        "{\"sfx\":[{\"speed\":2,\"steps\":[[57,0,7,5]]}]}") == 0, "fade bank");
    moy_audio_init(&a, &bank, RATE);
    moy_audio_sfx(&a, 0, -1);
    moy_audio_render(&a, buf, RATE / 2);
    check(rms(buf, RATE / 20) > 16.0f * rms(buf + RATE / 2 - RATE / 20, RATE / 20),
          "fade-out: the last 10%% is far quieter than the first");

    /* -- music claims from the top; sfx round-robins the rest ------- */
    check(moy_bank_parse(&bank,
        "{\"sfx\":[{\"loop\":true,\"steps\":[[40,0,6]]},"
        "         {\"loop\":true,\"steps\":[[45,1,6]]}],"
        " \"music\":[{\"speed\":4,\"pattern\":[[0,1]]}]}") == 0, "claim bank");
    moy_audio_init(&a, &bank, RATE);
    moy_audio_music(&a, 0, 1);
    check(a.v[3].owner == 2 && a.v[3].s == &bank.sfx[0],
          "row channel 0 plays on voice 3");
    check(a.v[2].owner == 2 && a.v[2].s == &bank.sfx[1],
          "row channel 1 plays on voice 2");
    moy_audio_sfx(&a, 0, -1);
    moy_audio_sfx(&a, 1, -1);
    check(a.v[0].owner == 1 && a.v[1].owner == 1,
          "sfx round-robin fills what music leaves free");
    check(a.v[2].owner == 2 && a.v[3].owner == 2,
          "sfx never steals a music channel");

    moy_audio_music_stop(&a);
    check(!a.v[2].owner && !a.v[3].owner && a.v[0].owner == 1,
          "music_stop releases only music voices");
    moy_audio_sound_stop(&a, -1);
    check(!a.v[0].owner && !a.v[1].owner, "sound_stop() stops everything");

    /* -- explicit channel, and stopping just it ---------------------- */
    moy_audio_sfx(&a, 0, 2);
    check(a.v[2].owner == 1, "sfx(n, 2) takes voice 2");
    moy_audio_sound_stop(&a, 2);
    check(!a.v[2].owner, "sound_stop(2) stops voice 2");

    /* -- a looping sfx does not end --------------------------------- */
    moy_audio_sfx(&a, 0, 0);
    moy_audio_render(&a, buf, RATE * 2);
    check(a.v[0].owner == 1, "a looping sfx still plays after 2s");
    moy_audio_sound_stop(&a, -1);

    /* -- vibrato wobbles a quarter semitone, not three ---------------- */
    check(moy_bank_parse(&bank,
        "{\"sfx\":[{\"speed\":4,\"loop\":true,\"steps\":[[57,0,7,2]]}]}") == 0,
        "vibrato bank");
    moy_audio_init(&a, &bank, RATE);
    moy_audio_sfx(&a, 0, 0);
    moy_audio_render(&a, buf, RATE);
    {
        /* A4 with vibrato: mean frequency stays ~440, every excursion within
         * +-0.25 semitone (~1.5%). Fractional-semitone math is only exercised
         * HERE and in slides -- integer notes cannot catch it. */
        int c = crossings(buf, RATE);
        check(c > 850 && c < 910, "vibrato stays centred on the note");
    }
    moy_audio_sound_stop(&a, -1);

    /* -- noise is pitched and smooth -------------------------------- */
    check(moy_bank_parse(&bank,
        "{\"sfx\":[{\"speed\":2,\"steps\":[[30,3,7]]},"
        "         {\"speed\":2,\"steps\":[[78,3,7]]}]}") == 0, "noise bank");
    moy_audio_init(&a, &bank, RATE);
    moy_audio_sfx(&a, 0, 0);
    moy_audio_render(&a, buf, RATE / 4);
    {
        int lo = crossings(buf, RATE / 4);
        int i, peak = 0;
        long dsum = 0;
        for (i = 1; i < RATE / 4; i++) {
            int d = buf[i] - buf[i - 1];
            dsum += d < 0 ? -d : d;
            if (buf[i] > peak) peak = buf[i];
        }
        moy_audio_sound_stop(&a, -1);
        moy_audio_sfx(&a, 1, 0);
        moy_audio_render(&a, buf, RATE / 4);
        check(crossings(buf, RATE / 4) > 3 * lo,
              "noise pitch scales its brightness");
        check(peak > 4000 && dsum / (RATE / 4) < peak / 8,
              "noise is interpolated, not white");
    }

    /* -- a slide's origin survives a retrigger (8.1: across rows) ---- */
    check(moy_bank_parse(&bank,
        "{\"sfx\":[{\"speed\":4,\"steps\":[[33,0,7]]},"
        "         {\"speed\":2,\"steps\":[[69,0,7,1]]}]}") == 0, "slide bank");
    moy_audio_init(&a, &bank, RATE);
    moy_audio_sfx(&a, 0, 0);            /* A2, finishes... */
    moy_audio_render(&a, buf, RATE / 4);
    moy_audio_sfx(&a, 1, 0);            /* ...then A5 with eff=slide */
    moy_audio_render(&a, buf, RATE / 2);
    {
        /* Gliding A2 -> A5 over 0.5 s: the first fifth is near 110 Hz, the
         * last fifth near 880 Hz -- a factor ~8, no factor at all if the
         * retrigger forgot the channel's previous note. */
        int head = crossings(buf, RATE / 10);
        int tail = crossings(buf + RATE / 2 - RATE / 10, RATE / 10);
        /* Halfway, a frequency-linear glide sits near (110+880)/2 = 495 Hz;
         * a semitone-linear one near 110*8^0.5 = 311 Hz. ~99 vs ~62
         * crossings in a tenth of a second. */
        int mid = crossings(buf + RATE / 4 - RATE / 20, RATE / 10);
        check(tail > 4 * head, "slide glides from the pre-retrigger note");
        check(mid > 80, "slide interpolates frequency, not semitones");
    }

    /* -- a keyed rest (vol 0) is a slide origin ----------------------- */
    check(moy_bank_parse(&bank,
        "{\"sfx\":[{\"speed\":4,\"steps\":[[33,0,7],[45,0,0]]}]}") == 0,
        "keyed-rest bank");
    moy_audio_init(&a, &bank, RATE);
    moy_audio_sfx(&a, 0, 0);
    moy_audio_render(&a, buf, RATE);
    check(a.v[0].prev_pitch == 45.0f && a.v[0].prev_vol == 0.0f,
          "a silent step with a key still sets the slide origin");

    /* -- arpeggio doubles on a fast sfx ------------------------------- */
    check(moy_bank_parse(&bank,
        "{\"sfx\":[{\"speed\":16,\"loop\":true,"
        "\"steps\":[[33,0,7,6],[57,0,7,6],[33,0,7,6],[57,0,7,6]]}]}") == 0,
        "arp bank");
    moy_audio_init(&a, &bank, RATE);
    moy_audio_sfx(&a, 0, 0);
    moy_audio_render(&a, buf, RATE / 4);
    {
        /* At 60 notes/s the window 1/60..2/60 s plays step 1 (A4): ~15
         * crossings. At the slow 30 notes/s it would still be on step 0
         * (A2): ~4. */
        int c = crossings(buf + RATE / 60, RATE / 60);
        check(c > 9, "fast-sfx arpeggio runs at 60 notes/s");
    }

    /* -- a 4-wide track: sfx steals voice 0, never drops -------------- */
    check(moy_bank_parse(&bank,
        "{\"sfx\":[{\"loop\":true,\"steps\":[[40,0,6]]}],"
        " \"music\":[{\"pattern\":[[0,0,0,0]]}]}") == 0, "full-claim bank");
    moy_audio_init(&a, &bank, RATE);
    moy_audio_music(&a, 0, 1);
    moy_audio_sfx(&a, 0, -1);
    check(a.v[0].owner == 1, "sfx on a full board steals voice 0");

    /* -- row_secs 0 holds the row ----------------------------------- */
    check(moy_bank_parse(&bank,
        "{\"sfx\":[{\"loop\":true,\"steps\":[[40,0,6]]}],"
        " \"music\":[{\"pattern\":[0],\"row_secs\":[0]}]}") == 0, "hold bank");
    moy_audio_init(&a, &bank, RATE);
    moy_audio_music(&a, 0, 0);          /* loop false: would end if it advanced */
    moy_audio_render(&a, buf, RATE * 2);
    check(a.track != NULL && a.v[3].owner == 2,
          "row_secs 0 holds the row forever");

    /* -- beep, and its end ------------------------------------------ */
    moy_audio_init(&a, &bank, RATE);
    moy_audio_beep(&a, 440.0f, 0.1f);
    moy_audio_render(&a, buf, RATE / 2);
    check(rms(buf, RATE / 10) > 0.0f, "beep makes sound");
    check(rms(buf + RATE / 4, RATE / 10) == 0.0f, "beep ends after dur");

    /* -- no bank: everything no-ops, render is silence --------------- */
    moy_audio_init(&a, NULL, RATE);
    moy_audio_sfx(&a, 0, -1);
    moy_audio_music(&a, 0, 1);
    moy_audio_beep(&a, -1.0f, 0.0f);
    moy_audio_render(&a, buf, RATE / 10);
    check(rms(buf, RATE / 10) == 0.0f, "no bank renders silence");

    if (failures) {
        fprintf(stderr, "%d audio checks failed\n", failures);
        return 1;
    }
    printf("audio: all checks passed\n");
    return 0;
}
