;; Refused: its memory is 2 pages and its manifest declares 4; the
;; block a host allocates is the manifest's, checked before it allocates.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (memory (export "memory") 2 2)
  (func (export "_init"))
  (func (export "_update") (param f32))
  (func (export "_draw") (call $cls (i32.const 1)))
)
