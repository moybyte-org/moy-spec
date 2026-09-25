;; Traps: at most one blit per _draw.
(module
  (import "moy" "blit" (func $blit (param i32 i32)))
  (memory (export "memory") 2 2)
  (func (export "_init"))
  (func (export "_update") (param f32))
  (func (export "_draw")
    (call $blit (i32.const 0) (i32.const 0))
    (call $blit (i32.const 0) (i32.const 0))))
