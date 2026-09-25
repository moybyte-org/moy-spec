;; Refused: no _draw export; all four exports are required.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (memory (export "memory") 1 1)
  (func (export "_init"))
  (func (export "_update") (param f32) (call $cls (i32.const 1)))
)
