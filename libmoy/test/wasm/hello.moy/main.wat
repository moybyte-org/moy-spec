;; The conforming fixture: a runtime "wasm" cart that `moy check` passes and
;; libmoy's binding runs under WAMR (make wasm-test). _init reports what it
;; reads through pmem -- the harness's host records every pmem write -- and
;; _draw blits a 256-colour frame and draws three verbs over it, which
;; test/wasm_frame.py renders independently through moycore.
;;
;; Memory: page 0 holds strings at 1024, the out buffer at 4096, the read
;; buffer at 4200, the cfg buffer at 4300, the samples at 4400 and the palette
;; at 8192; the frame is page 1 onward (76,800 bytes from 65536). Three pages,
;; min = max.
(module
  (import "moy" "cls" (func $cls (param i32)))
  (import "moy" "pix" (func $pix (param i32 i32 i32) (result i32)))
  (import "moy" "rect" (func $rect (param i32 i32 i32 i32 i32)))
  (import "moy" "circ" (func $circ (param i32 i32 i32 i32)))
  (import "moy" "print" (func $print (param i32 i32 i32 i32 i32)))
  (import "moy" "camera" (func $camera (param i32 i32 i32)))
  (import "moy" "make_layer" (func $make_layer (param i32 i32) (result i32)))
  (import "moy" "target" (func $target (param i32)))
  (import "moy" "fget" (func $fget (param i32 i32) (result i32)))
  (import "moy" "fset" (func $fset (param i32 i32 i32)))
  (import "moy" "btn" (func $btn (param i32 i32) (result i32)))
  (import "moy" "touch" (func $touch (param i32) (result i32)))
  (import "moy" "time" (func $time (result i32)))
  (import "moy" "pmem" (func $pmem (param i32 i32 i32) (result i32)))
  (import "moy" "cfg" (func $cfg (param i32 i32 i32 i32) (result i32)))
  (import "moy" "flr" (func $flr (param f32) (result i32)))
  (import "moy" "read" (func $read (param i32 i32 i32 i32 i32) (result i32)))
  (import "moy" "blit" (func $blit (param i32 i32)))
  (import "moy" "snd" (func $snd (param i32 i32) (result i32)))

  (memory (export "memory") 3 3)

  (data (i32.const 1024) "HELLO")
  (data (i32.const 1040) "greeting.txt")
  (data (i32.const 1056) "../manifest.json")
  (data (i32.const 1088) "missing.txt")
  (data (i32.const 1104) "speed")
  (data (i32.const 1112) "nope")

  (global $layer (mut i32) (i32.const 0))

  ;; pmem(slot, v, 1): the harness's record of what the cart saw.
  (func $report (param $slot i32) (param $v i32)
    (drop (call $pmem (local.get $slot) (local.get $v) (i32.const 1))))

  (func (export "_init") (local $i i32)
    ;; a layer, drawn into through target, read back on the layer
    (global.set $layer (call $make_layer (i32.const 64) (i32.const 32)))
    (call $report (i32.const 0) (global.get $layer))
    (call $target (global.get $layer))
    (call $cls (i32.const 8))
    (call $circ (i32.const 16) (i32.const 16) (i32.const 10) (i32.const 12))
    (call $report (i32.const 1)
      (call $pix (i32.const 16) (i32.const 16) (i32.const -1)))
    (call $target (i32.const 0))

    ;; the cart's own files: a read, a size, an escape, an absence
    (call $report (i32.const 2)
      (call $read (i32.const 1040) (i32.const 12) (i32.const 0)
                  (i32.const 4200) (i32.const 16)))
    (call $report (i32.const 3) (i32.load8_u (i32.const 4200)))
    (call $report (i32.const 4)
      (call $read (i32.const 1040) (i32.const 12) (i32.const 0)
                  (i32.const 0) (i32.const 0)))
    (call $report (i32.const 5)
      (call $read (i32.const 1056) (i32.const 16) (i32.const 0)
                  (i32.const 4200) (i32.const 16)))
    (call $report (i32.const 6)
      (call $read (i32.const 1088) (i32.const 11) (i32.const 0)
                  (i32.const 4200) (i32.const 16)))

    ;; camera's previous offset through the out pointer
    (call $camera (i32.const 7) (i32.const 9) (i32.const 0))
    (call $camera (i32.const 0) (i32.const 0) (i32.const 4096))
    (call $report (i32.const 7) (i32.load (i32.const 4096)))
    (call $report (i32.const 8) (i32.load (i32.const 4100)))

    ;; input: button a (index 4) is held by the harness; there is no pointer
    (call $report (i32.const 9) (call $btn (i32.const 4) (i32.const 0)))
    (call $report (i32.const 10) (call $touch (i32.const 4096)))

    ;; cfg: a present key's length, and -1 for an absent one
    (call $report (i32.const 11)
      (call $cfg (i32.const 1104) (i32.const 5) (i32.const 4300) (i32.const 16)))
    (call $report (i32.const 12) (i32.load8_u (i32.const 4300)))
    (call $report (i32.const 13)
      (call $cfg (i32.const 1112) (i32.const 4) (i32.const 4300) (i32.const 16)))

    ;; flags: the byte form and the bit form
    (call $fset (i32.const 3) (i32.const -1) (i32.const 0x81))
    (call $report (i32.const 14) (call $fget (i32.const 3) (i32.const -1)))
    (call $report (i32.const 15) (call $fget (i32.const 3) (i32.const 7)))

    (call $report (i32.const 16) (call $flr (f32.const -1.5)))
    (call $report (i32.const 17) (call $time))

    ;; the sample stream, on a host with no audio and a clock that stands:
    ;; the room, a hundred frames queued, and the room left
    (call $report (i32.const 19) (call $snd (i32.const 0) (i32.const 0)))
    (call $report (i32.const 20) (call $snd (i32.const 4400) (i32.const 100)))
    (call $report (i32.const 21) (call $snd (i32.const 0) (i32.const 0)))

    ;; the frame's palette: entry i is (i, 255 - i, 2i mod 256)
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 256)))
        (i32.store8 offset=8192 (i32.mul (local.get $i) (i32.const 3))
                    (local.get $i))
        (i32.store8 offset=8193 (i32.mul (local.get $i) (i32.const 3))
                    (i32.sub (i32.const 255) (local.get $i)))
        (i32.store8 offset=8194 (i32.mul (local.get $i) (i32.const 3))
                    (i32.and (i32.shl (local.get $i) (i32.const 1))
                             (i32.const 255)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each))))

  (func (export "_update") (param $dt f32)
    (call $report (i32.const 18)
      (i32.trunc_f32_s (f32.mul (local.get $dt) (f32.const 1000)))))

  (func (export "_draw") (local $i i32)
    ;; frame[y * 320 + x] = (x + y) mod 256
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 76800)))
        (i32.store8 offset=65536 (local.get $i)
          (i32.add (i32.rem_u (local.get $i) (i32.const 320))
                   (i32.div_u (local.get $i) (i32.const 320))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))
    (call $blit (i32.const 65536) (i32.const 8192))
    (call $rect (i32.const 10) (i32.const 10) (i32.const 50) (i32.const 30)
                (i32.const 8))
    (call $circ (i32.const 160) (i32.const 120) (i32.const 20) (i32.const 12))
    (call $print (i32.const 1024) (i32.const 5) (i32.const 100) (i32.const 200)
                 (i32.const 7)))
)
