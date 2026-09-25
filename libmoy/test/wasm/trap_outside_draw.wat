;; Traps: blit is legal only inside _draw, and this one runs in _update.
(module
  (import "moy" "blit" (func $blit (param i32 i32)))
  (memory (export "memory") 2 2)
  (func (export "_init"))
  (func (export "_update") (param f32)
    (call $blit (i32.const 0) (i32.const 0)))
  (func (export "_draw")))
