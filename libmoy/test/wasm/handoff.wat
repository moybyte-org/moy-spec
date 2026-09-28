;; The frame hand-off (include/moy_wasm.h, `frame`): what _draw does is picked
;; by the _update before it, whose dt * 1000 is the mode. wasm_test.c drives
;; one sequence of modes through a host that takes every frame and through a
;; host that takes none, and holds every screen the two leave to be the same.
;;
;;   1  blit              2  blit, then rect     3  rect alone
;;   4  blit565           5  blit565, then rect  6  blit, then pix reads (1, 1)
;;   7  blit, then cls    8  blit, then a trap
;;
;; Every frame differs from the one before it (`seed`), so a stale frame never
;; reads as the right one. Memory: the palette at 8192, the frame from 65536 --
;; 76,800 index bytes or 153,600 bytes of RGB565 words. Four pages.
(module
  (import "moy" "blit" (func $blit (param i32 i32)))
  (import "moy" "blit565" (func $blit565 (param i32)))
  (import "moy" "rect" (func $rect (param i32 i32 i32 i32 i32)))
  (import "moy" "cls" (func $cls (param i32)))
  (import "moy" "pix" (func $pix (param i32 i32 i32) (result i32)))
  (import "moy" "pmem" (func $pmem (param i32 i32 i32) (result i32)))

  (memory (export "memory") 4 4)
  (global $mode (mut i32) (i32.const 0))
  (global $seed (mut i32) (i32.const 0))

  ;; frame[i] = (x + y + seed) mod 256, one byte a pixel
  (func $indices (local $i i32)
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 76800)))
        (i32.store8 offset=65536 (local.get $i)
          (i32.add (global.get $seed)
            (i32.add (i32.rem_u (local.get $i) (i32.const 320))
                     (i32.div_u (local.get $i) (i32.const 320)))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each))))

  ;; frame[i] = i * 37 + seed * 101, one little-endian word a pixel
  (func $words (local $i i32)
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 76800)))
        (i32.store16 offset=65536 (i32.shl (local.get $i) (i32.const 1))
          (i32.add (i32.mul (local.get $i) (i32.const 37))
                   (i32.mul (global.get $seed) (i32.const 101))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each))))

  ;; palette[i] = (i, 255 - i, 2i mod 256)
  (func (export "_init") (local $i i32)
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 256)))
        (i32.store8 offset=8192 (i32.mul (local.get $i) (i32.const 3))
                    (local.get $i))
        (i32.store8 offset=8193 (i32.mul (local.get $i) (i32.const 3))
                    (i32.sub (i32.const 255) (local.get $i)))
        (i32.store8 offset=8194 (i32.mul (local.get $i) (i32.const 3))
                    (i32.and (i32.shl (local.get $i) (i32.const 1))
                             (i32.const 255)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each))))

  (func (export "_update") (param $dt f32)
    (global.set $mode
      (i32.trunc_f32_s (f32.add (f32.mul (local.get $dt) (f32.const 1000))
                                (f32.const 0.5)))))

  (func (export "_draw")
    (global.set $seed (i32.add (global.get $seed) (i32.const 1)))
    (if (i32.eq (global.get $mode) (i32.const 3))
      (then
        (call $rect (i32.const 20) (i32.const 20) (i32.const 30) (i32.const 30)
                    (i32.const 12))
        (return)))
    (if (i32.or (i32.eq (global.get $mode) (i32.const 4))
                (i32.eq (global.get $mode) (i32.const 5)))
      (then
        (call $words)
        (call $blit565 (i32.const 65536)))
      (else
        (call $indices)
        (call $blit (i32.const 65536) (i32.const 8192))))
    (if (i32.or (i32.eq (global.get $mode) (i32.const 2))
                (i32.eq (global.get $mode) (i32.const 5)))
      (then
        (call $rect (i32.const 10) (i32.const 10) (i32.const 50) (i32.const 30)
                    (i32.const 8))))
    (if (i32.eq (global.get $mode) (i32.const 6))
      (then
        (drop (call $pmem (i32.const 0)
                          (call $pix (i32.const 1) (i32.const 1) (i32.const -1))
                          (i32.const 1)))))
    (if (i32.eq (global.get $mode) (i32.const 7))
      (then (call $cls (i32.const 3))))
    (if (i32.eq (global.get $mode) (i32.const 8))
      (then (unreachable))))
)
