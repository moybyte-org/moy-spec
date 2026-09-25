;; quit() ends the cart without a trap: _update returns success to the host,
;; which has been told through its quit hook, and the cls after it never runs.
(module
  (import "moy" "quit" (func $quit))
  (import "moy" "cls" (func $cls (param i32)))
  (memory (export "memory") 1 1)
  (func (export "_init"))
  (func (export "_update") (param f32)
    (call $quit)
    (call $cls (i32.const 5)))
  (func (export "_draw")))
