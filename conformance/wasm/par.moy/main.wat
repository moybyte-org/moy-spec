;; par (SPEC.md 16.10, "The cart's own work across the cores"):
;; _draw hands par eight items, each the RGB565 words of thirty rows of the
;; frame, then blits it. A host runs them on any of its cores, at once or one
;; after another, and the frame is the same: this golden is every host's.
;;
;; Item i records the stack pointer it was given; after par, a bar for each
;; item is green (11) when that was the top of its own 1 KiB -- stacks + (i +
;; 1) * 1024 -- and red (8) when not, and a last bar says the same of the
;; caller's stack pointer, which par puts back. The circle drawn before the
;; blit is gone; the bars drawn after it are on top.
;;
;; Memory: the stack pointers seen at 1024, the stacks from 8192, the frame
;; from 65536 (153,600 bytes). Four pages.
(module
  (import "moy" "par" (func $par (param i32 i32 i32 i32)))
  (import "moy" "blit565" (func $blit565 (param i32)))
  (import "moy" "rect" (func $rect (param i32 i32 i32 i32 i32)))
  (import "moy" "circ" (func $circ (param i32 i32 i32 i32)))

  (memory (export "memory") 4 4)
  (global $sp (export "__stack_pointer") (mut i32) (i32.const 4096))

  ;; word(x, y) = ((3x + 5i) & 31) << 11 | ((2y + 7i) & 63) << 5 | ((x ^ y) & 31)
  (func (export "_par") (param $i i32) (param $arg i32)
        (local $x i32) (local $y i32) (local $end i32)
    (i32.store offset=1024 (i32.shl (local.get $i) (i32.const 2)) (global.get $sp))
    (local.set $y (i32.mul (local.get $i) (i32.const 30)))
    (local.set $end (i32.add (local.get $y) (i32.const 30)))
    (block $rows
      (loop $row
        (br_if $rows (i32.ge_u (local.get $y) (local.get $end)))
        (local.set $x (i32.const 0))
        (block $cols
          (loop $col
            (br_if $cols (i32.ge_u (local.get $x) (i32.const 320)))
            (i32.store16 offset=65536
              (i32.shl (i32.add (i32.mul (local.get $y) (i32.const 320)) (local.get $x))
                       (i32.const 1))
              (i32.or
                (i32.or
                  (i32.shl (i32.and (i32.add (i32.mul (local.get $x) (local.get $arg))
                                             (i32.mul (local.get $i) (i32.const 5)))
                                    (i32.const 31))
                           (i32.const 11))
                  (i32.shl (i32.and (i32.add (i32.shl (local.get $y) (i32.const 1))
                                             (i32.mul (local.get $i) (i32.const 7)))
                                    (i32.const 63))
                           (i32.const 5)))
                (i32.and (i32.xor (local.get $x) (local.get $y)) (i32.const 31))))
            (local.set $x (i32.add (local.get $x) (i32.const 1)))
            (br $col)))
        (local.set $y (i32.add (local.get $y) (i32.const 1)))
        (br $row))))

  (func (export "_init"))
  (func (export "_update") (param f32))

  (func (export "_draw") (local $k i32)
    (call $circ (i32.const 160) (i32.const 120) (i32.const 30) (i32.const 12))
    (call $par (i32.const 8) (i32.const 3) (i32.const 8192) (i32.const 1024))
    (call $blit565 (i32.const 65536))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $k) (i32.const 8)))
        (call $rect (i32.add (i32.const 4) (i32.mul (local.get $k) (i32.const 20)))
                    (i32.const 4) (i32.const 16) (i32.const 8)
                    (select (i32.const 11) (i32.const 8)
                            (i32.eq (i32.load offset=1024 (i32.shl (local.get $k) (i32.const 2)))
                                    (i32.add (i32.const 8192)
                                             (i32.mul (i32.add (local.get $k) (i32.const 1))
                                                      (i32.const 1024))))))
        (local.set $k (i32.add (local.get $k) (i32.const 1)))
        (br $each)))
    (call $rect (i32.const 170) (i32.const 4) (i32.const 16) (i32.const 8)
                (select (i32.const 11) (i32.const 8)
                        (i32.eq (global.get $sp) (i32.const 4096)))))
)
