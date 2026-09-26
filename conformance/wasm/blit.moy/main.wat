;; blit with a 256-entry palette (proposals/wasm-runtime.md, "The framebuffer
;; contract"). Every one of the 256 indices is on screen, each through the
;; palette handed over with the frame. What the scene holds a host to:
;;
;;   - the blit replaces the whole screen, so the cls and the rect drawn
;;     before it are gone;
;;   - it ignores the draw state and the target: camera, clip and pal are set
;;     and the target is a layer when it is called, and the frame still lands
;;     whole, on the screen;
;;   - draw order is call order: the HUD drawn after it is on top, through the
;;     camera, clip and pal still in force.
;;
;; Memory: the HUD's text at 1024, the palette at 4096 (768 bytes), the frame
;; from 65536 (76,800 bytes). Three pages.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (import "moy" "rect" (func $rect (param i32 i32 i32 i32 i32)))
  (import "moy" "print" (func $print (param i32 i32 i32 i32 i32)))
  (import "moy" "camera" (func $camera (param i32 i32 i32)))
  (import "moy" "clip" (func $clip (param i32 i32 i32 i32)))
  (import "moy" "pal" (func $pal (param i32 i32 i32)))
  (import "moy" "make_layer" (func $make_layer (param i32 i32) (result i32)))
  (import "moy" "target" (func $target (param i32)))
  (import "moy" "blit" (func $blit (param i32 i32)))

  (memory (export "memory") 3 3)
  (data (i32.const 1024) "256 COLOURS")
  (global $layer (mut i32) (i32.const 0))

  (func (export "_init") (local $i i32)
    (global.set $layer (call $make_layer (i32.const 320) (i32.const 240)))
    ;; entry i: (i, 37i mod 256, 255 - i)
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 256)))
        (i32.store8 offset=4096 (i32.mul (local.get $i) (i32.const 3))
                    (local.get $i))
        (i32.store8 offset=4097 (i32.mul (local.get $i) (i32.const 3))
                    (i32.and (i32.mul (local.get $i) (i32.const 37))
                             (i32.const 255)))
        (i32.store8 offset=4098 (i32.mul (local.get $i) (i32.const 3))
                    (i32.sub (i32.const 255) (local.get $i)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each))))

  (func (export "_update") (param f32))

  (func (export "_draw") (local $i i32)
    ;; frame[y * 320 + x] = (3x + 5y) mod 256
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 76800)))
        (i32.store8 offset=65536 (local.get $i)
          (i32.add
            (i32.mul (i32.rem_u (local.get $i) (i32.const 320)) (i32.const 3))
            (i32.mul (i32.div_u (local.get $i) (i32.const 320)) (i32.const 5))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))
    (call $cls (i32.const 9))
    (call $rect (i32.const 0) (i32.const 0) (i32.const 50) (i32.const 50) (i32.const 3))
    (call $camera (i32.const 6) (i32.const 4) (i32.const 0))
    (call $clip (i32.const 0) (i32.const 0) (i32.const 100) (i32.const 100))
    (call $pal (i32.const 8) (i32.const 12) (i32.const 0))
    (call $target (global.get $layer))
    (call $blit (i32.const 65536) (i32.const 4096))
    (call $target (i32.const 0))
    (call $rect (i32.const 6) (i32.const 4) (i32.const 120) (i32.const 12) (i32.const 8))
    (call $print (i32.const 1024) (i32.const 11) (i32.const 8) (i32.const 6)
                 (i32.const 7)))
)
