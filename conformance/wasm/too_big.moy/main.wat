;; A conforming module that declares the most memory wasm32 has: 65,536 pages,
;; 4 GiB. Its shape is the proposal's and `moy check` passes it; what it asks
;; for is more than any player here gives a cart, so each refuses it before
;; anything of it is allocated, with a plain sentence and no frame.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (memory (export "memory") 65536 65536)
  (func (export "_init"))
  (func (export "_update") (param f32))
  (func (export "_draw") (call $cls (i32.const 1)))
)
