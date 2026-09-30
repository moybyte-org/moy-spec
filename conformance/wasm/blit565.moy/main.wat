;; blit565 (SPEC.md 16.5): a direct-colour frame of
;; little-endian RGB565 words, every channel ramped across the screen. It is
;; already in the golden's form, so the scene holds a host to showing exactly
;; the words it was handed: the byte order is the spec's, not the panel's.
;; The circle drawn before it is gone; the ring and the text drawn after it
;; are on top.
;;
;; Memory: the text at 1024, the frame from 65536 (153,600 bytes). Four pages.
(module
  (import "moy" "circ" (func $circ (param i32 i32 i32 i32)))
  (import "moy" "circb" (func $circb (param i32 i32 i32 i32)))
  (import "moy" "print" (func $print (param i32 i32 i32 i32 i32)))
  (import "moy" "blit565" (func $blit565 (param i32)))

  (memory (export "memory") 4 4)
  (data (i32.const 1024) "RGB565")

  (func (export "_init"))
  (func (export "_update") (param f32))

  (func (export "_draw") (local $i i32) (local $x i32) (local $y i32)
    ;; word(x, y) = (x / 10) << 11 | (63y / 239) << 5 | ((x + y) & 31)
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 76800)))
        (local.set $x (i32.rem_u (local.get $i) (i32.const 320)))
        (local.set $y (i32.div_u (local.get $i) (i32.const 320)))
        (i32.store16 offset=65536 (i32.shl (local.get $i) (i32.const 1))
          (i32.or
            (i32.or
              (i32.shl (i32.div_u (local.get $x) (i32.const 10)) (i32.const 11))
              (i32.shl (i32.div_u (i32.mul (local.get $y) (i32.const 63))
                                  (i32.const 239))
                       (i32.const 5)))
            (i32.and (i32.add (local.get $x) (local.get $y)) (i32.const 31))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))
    (call $circ (i32.const 160) (i32.const 120) (i32.const 30) (i32.const 12))
    (call $blit565 (i32.const 65536))
    (call $circb (i32.const 160) (i32.const 120) (i32.const 40) (i32.const 7))
    (call $print (i32.const 1024) (i32.const 6) (i32.const 136) (i32.const 116)
                 (i32.const 7)))
)
