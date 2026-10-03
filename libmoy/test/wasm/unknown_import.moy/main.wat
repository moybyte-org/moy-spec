;; Refused: it imports later from "moy", a name the table does not have --
;; what a cart built for a newer table looks like to a host built before it.
;; Refused at load, by name; never linked and left to trap when it is called.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (import "moy" "later" (func $later (param i32) (result i32)))
  (memory (export "memory") 1 1)
  (func (export "_init"))
  (func (export "_update") (param f32))
  (func (export "_draw") (call $cls (i32.const 1)))
)
