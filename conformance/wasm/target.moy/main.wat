;; target (proposals/wasm-runtime.md, "Marshalling"): a compiled cart's
;; receiver for a Lua layer's methods. The scene holds one full-screen layer,
;; the one SPEC.md 1.1 guarantees, and holds a host to:
;;
;;   - target(layer) points the drawing verbs at the layer, target(0) back at
;;     the screen, and the screen is the target again whenever a hook starts;
;;   - a layer keeps its own draw state: the camera set on it in _init still
;;     moves what _draw puts there, and never moves the screen;
;;   - pix reads the layer back while it is the target;
;;   - a layer keeps its pixels between frames: the square drawn into it after
;;     draw_layer is not on this frame's screen and is on the next one's.
;;
;; Run for two frames, as every scene is (conformance/wasm_run.py).
(module
  (import "moy" "cls" (func $cls (param i32)))
  (import "moy" "pix" (func $pix (param i32 i32 i32) (result i32)))
  (import "moy" "rect" (func $rect (param i32 i32 i32 i32 i32)))
  (import "moy" "rectb" (func $rectb (param i32 i32 i32 i32 i32)))
  (import "moy" "circ" (func $circ (param i32 i32 i32 i32)))
  (import "moy" "print" (func $print (param i32 i32 i32 i32 i32)))
  (import "moy" "camera" (func $camera (param i32 i32 i32)))
  (import "moy" "make_layer" (func $make_layer (param i32 i32) (result i32)))
  (import "moy" "draw_layer" (func $draw_layer (param i32 i32 i32)))
  (import "moy" "target" (func $target (param i32)))

  (memory (export "memory") 1 1)
  (data (i32.const 1024) "LAYER")
  (global $layer (mut i32) (i32.const 0))
  (global $seen (mut i32) (i32.const 0))

  (func (export "_init")
    (global.set $layer (call $make_layer (i32.const 320) (i32.const 240)))
    (call $target (global.get $layer))
    (call $cls (i32.const 2))
    (call $camera (i32.const -10) (i32.const -10) (i32.const 0))
    (call $circ (i32.const 50) (i32.const 50) (i32.const 20) (i32.const 9))
    (call $rectb (i32.const 0) (i32.const 0) (i32.const 100) (i32.const 60) (i32.const 11))
    (call $print (i32.const 1024) (i32.const 5) (i32.const 20) (i32.const 90) (i32.const 7))
    (global.set $seen (call $pix (i32.const 60) (i32.const 60) (i32.const -1)))
    (call $target (i32.const 0)))

  (func (export "_update") (param f32))

  (func (export "_draw")
    (call $cls (i32.const 5))
    (call $target (global.get $layer))
    (drop (call $pix (i32.const 0) (i32.const 0) (i32.const 14)))
    (call $target (i32.const 0))
    (call $draw_layer (global.get $layer) (i32.const 0) (i32.const 0))
    (call $camera (i32.const 3) (i32.const 3) (i32.const 0))
    (call $rect (i32.const 0) (i32.const 0) (i32.const 16) (i32.const 16) (global.get $seen))
    (call $camera (i32.const 0) (i32.const 0) (i32.const 0))
    (call $target (global.get $layer))
    (call $rect (i32.const 200) (i32.const 150) (i32.const 30) (i32.const 30) (i32.const 6))
    (call $target (i32.const 0))
    (call $rect (i32.const 300) (i32.const 220) (i32.const 20) (i32.const 20) (i32.const 14)))
)
