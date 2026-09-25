;; Traps: 5 is a layer handle make_layer never returned.
(module
  (import "moy" "target" (func $target (param i32)))
  (memory (export "memory") 1 1)
  (func (export "_init") (call $target (i32.const 5)))
  (func (export "_update") (param f32))
  (func (export "_draw")))
