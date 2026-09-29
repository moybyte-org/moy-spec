;; A trap in one of par's items (proposals/wasm-runtime.md, "The cart's own
;; work across the cores"): it traps the call to par, and so the cart. Each
;; _draw hands par four items, each a quarter of the frame's rows in one
;; colour, and blits the frame. In the second, item 2 reaches unreachable after
;; filling its rows, whichever core it ran on; a host ends the cart -- a player
;; exits non-zero -- and the frame it shows, and writes, is the first one.
;;
;; Memory: the stacks from 8192, the frame from 65536. Four pages.
(module
  (import "moy" "par" (func $par (param i32 i32 i32 i32)))
  (import "moy" "blit565" (func $blit565 (param i32)))

  (memory (export "memory") 4 4)
  (global $sp (export "__stack_pointer") (mut i32) (i32.const 4096))
  (global $frame (mut i32) (i32.const 0))

  ;; rows [60i, 60i + 60) in colour 0x1F << (5i) & 0xFFFF, once more each frame
  (func (export "_par") (param $i i32) (param $frame i32) (local $p i32) (local $end i32)
    (local.set $p (i32.add (i32.const 65536) (i32.mul (local.get $i) (i32.const 38400))))
    (local.set $end (i32.add (local.get $p) (i32.const 38400)))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $p) (local.get $end)))
        (i32.store16 (local.get $p)
          (i32.add (i32.mul (local.get $i) (i32.const 8191)) (local.get $frame)))
        (local.set $p (i32.add (local.get $p) (i32.const 2)))
        (br $each)))
    (if (i32.and (i32.eq (local.get $frame) (i32.const 2)) (i32.eq (local.get $i) (i32.const 2)))
      (then unreachable)))

  (func (export "_init"))
  (func (export "_update") (param f32))

  (func (export "_draw")
    (global.set $frame (i32.add (global.get $frame) (i32.const 1)))
    (call $par (i32.const 4) (global.get $frame) (i32.const 8192) (i32.const 1024))
    (call $blit565 (i32.const 65536)))
)
