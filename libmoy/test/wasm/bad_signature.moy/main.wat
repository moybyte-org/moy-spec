;; Refused: cls is imported at (f32) -> (); the table says (i32) -> ().
(module
  (import "moy" "cls" (func $cls (param f32)))
  (memory (export "memory") 1 1)
  (func (export "_init"))
  (func (export "_update") (param f32))
  (func (export "_draw") (call $cls (f32.const 1)))
)
