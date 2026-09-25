;; Refused: it imports from a module other than "moy", the one
;; capability surface a compiled cart has.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (import "env" "sleep_ms" (func $sleep (param i32)))
  (memory (export "memory") 1 1)
  (func (export "_init"))
  (func (export "_update") (param f32))
  (func (export "_draw") (call $cls (i32.const 1)))
)
