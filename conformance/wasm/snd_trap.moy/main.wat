;; snd past the memory (proposals/wasm-runtime.md, "PCM audio"): a range of
;; samples that leaves linear memory is a trap. The first _draw finishes; the
;; second repaints the screen and hands snd eight frames that run four bytes
;; past the end. A host ends the cart -- a player exits non-zero -- and the
;; frame it shows, and writes, is the first one.
(module
  (import "moy" "snd" (func $snd (param i32 i32) (result i32)))
  (import "moy" "cls" (func $cls (param i32)))
  (import "moy" "circ" (func $circ (param i32 i32 i32 i32)))

  (memory (export "memory") 1 1)
  (global $frame (mut i32) (i32.const 0))

  (func (export "_init"))
  (func (export "_update") (param f32))

  (func (export "_draw")
    (global.set $frame (i32.add (global.get $frame) (i32.const 1)))
    (if (i32.eq (global.get $frame) (i32.const 1))
      (then
        (call $cls (i32.const 12))
        (call $circ (i32.const 160) (i32.const 120) (i32.const 40) (i32.const 7)))
      (else
        (call $cls (i32.const 8))
        (drop (call $snd (i32.const 65524) (i32.const 8))))))
)
