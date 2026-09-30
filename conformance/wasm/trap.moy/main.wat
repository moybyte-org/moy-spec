;; A trap (SPEC.md 16.8, "Traps"): the frame it interrupts is
;; never presented. The first _draw finishes; the second repaints the whole
;; screen and then traps. A host ends the cart -- a player exits non-zero --
;; and the frame it shows, and writes, is the first one.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (import "moy" "rect" (func $rect (param i32 i32 i32 i32 i32)))
  (import "moy" "circ" (func $circ (param i32 i32 i32 i32)))

  (memory (export "memory") 1 1)
  (global $frame (mut i32) (i32.const 0))

  (func (export "_init"))
  (func (export "_update") (param f32))

  (func (export "_draw")
    (global.set $frame (i32.add (global.get $frame) (i32.const 1)))
    (if (i32.eq (global.get $frame) (i32.const 1))
      (then
        (call $cls (i32.const 3))
        (call $circ (i32.const 160) (i32.const 120) (i32.const 50) (i32.const 10)))
      (else
        (call $cls (i32.const 8))
        (call $rect (i32.const 20) (i32.const 20) (i32.const 100) (i32.const 100) (i32.const 1))
        unreachable)))
)
