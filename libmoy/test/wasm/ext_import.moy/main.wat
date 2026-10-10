;; A vendor extension's import (SPEC.md 16.2): it imports from module
;; "test.ext", which its manifest declares. Refused by a host that carries no
;; such extension; typed against the extension's table by one that does.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (import "test.ext" "ping" (func $ping (param i32) (result i32)))
  (memory (export "memory") 1 1)
  (func (export "_init"))
  (func (export "_update") (param f32))
  (func (export "_draw") (call $cls (call $ping (i32.const 1))))
)
