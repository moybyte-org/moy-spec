;; Traps: a 320 x 240 frame from offset 65000 runs past this module's one
;; page of linear memory, and the host checks the range before it reads.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (import "moy" "blit" (func $blit (param i32 i32)))
  (memory (export "memory") 1 1)
  (func (export "_init"))
  (func (export "_update") (param f32))
  (func (export "_draw")
    (call $cls (i32.const 9))
    (call $blit (i32.const 65000) (i32.const 0))))
