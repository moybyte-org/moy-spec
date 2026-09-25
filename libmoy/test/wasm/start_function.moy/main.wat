;; Refused: a start function runs before _init, and nothing may.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (memory (export "memory") 1 1)
  (func $early (call $cls (i32.const 2)))
  (start $early)
  (func (export "_init"))
  (func (export "_update") (param f32))
  (func (export "_draw") (call $cls (i32.const 1)))
)
