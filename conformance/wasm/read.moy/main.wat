;; read (SPEC.md 16.6, "The cart's own files"): the
;; cart's own folder, its subfolders included, and nothing else. _init asks
;; fifteen questions of it, each answer is drawn as a bar in _draw, and the
;; bytes it read are the frame. What the scene holds a host to:
;;
;;   - len 0 answers the bytes remaining from offset (the size, at 0);
;;   - a read copies at most len and answers what it copied, short at the end
;;     and 0 at or past it;
;;   - an absent name, a folder, and every name the rule refuses -- "..", ".",
;;     an empty segment, a backslash, a leading "/" -- read 0;
;;   - a file in a subfolder reads by its '/'-separated path.
;;
;; A bar is 18 pixels wide; its height is (answer mod 64) + 1 and its colour 8
;; + answer / 64, so every answer below 512 draws its own bar.
;;
;; Memory: names from 1024, answers at 4096 (four bytes each), data.bin at
;; 8192, the short read at 9000, note.txt at 9200, the frame from 65536.
(module
  (import "moy" "read" (func $read (param i32 i32 i32 i32 i32) (result i32)))
  (import "moy" "rect" (func $rect (param i32 i32 i32 i32 i32)))
  (import "moy" "print" (func $print (param i32 i32 i32 i32 i32)))
  (import "moy" "blit" (func $blit (param i32 i32)))

  (memory (export "memory") 3 3)
  (data (i32.const 1024) "data.bin")
  (data (i32.const 1040) "nothing.bin")
  (data (i32.const 1056) "../read.moy/data.bin")
  (data (i32.const 1080) "./data.bin")
  (data (i32.const 1096) "sub//note.txt")
  (data (i32.const 1112) "sub\\note.txt")
  (data (i32.const 1128) "sub/note.txt")
  (data (i32.const 1144) "/data.bin")
  (data (i32.const 1160) "sub")

  ;; answer k = read(name, len, offset, dst, n)
  (func $ask (param $k i32) (param $name i32) (param $len i32) (param $off i32)
             (param $dst i32) (param $n i32)
    (i32.store offset=4096 (i32.shl (local.get $k) (i32.const 2))
      (call $read (local.get $name) (local.get $len) (local.get $off)
                  (local.get $dst) (local.get $n))))

  (func (export "_init")
    (call $ask (i32.const 0) (i32.const 1024) (i32.const 8) (i32.const 0) (i32.const 0) (i32.const 0))
    (call $ask (i32.const 1) (i32.const 1024) (i32.const 8) (i32.const 0) (i32.const 8192) (i32.const 256))
    (call $ask (i32.const 2) (i32.const 1024) (i32.const 8) (i32.const 250) (i32.const 9000) (i32.const 16))
    (call $ask (i32.const 3) (i32.const 1024) (i32.const 8) (i32.const 100) (i32.const 0) (i32.const 0))
    (call $ask (i32.const 4) (i32.const 1024) (i32.const 8) (i32.const 300) (i32.const 9100) (i32.const 16))
    (call $ask (i32.const 5) (i32.const 1024) (i32.const 8) (i32.const 256) (i32.const 9100) (i32.const 16))
    (call $ask (i32.const 6) (i32.const 1040) (i32.const 11) (i32.const 0) (i32.const 9100) (i32.const 16))
    (call $ask (i32.const 7) (i32.const 1056) (i32.const 20) (i32.const 0) (i32.const 9100) (i32.const 16))
    (call $ask (i32.const 8) (i32.const 1080) (i32.const 10) (i32.const 0) (i32.const 9100) (i32.const 16))
    (call $ask (i32.const 9) (i32.const 1096) (i32.const 13) (i32.const 0) (i32.const 9100) (i32.const 16))
    (call $ask (i32.const 10) (i32.const 1112) (i32.const 12) (i32.const 0) (i32.const 9100) (i32.const 16))
    (call $ask (i32.const 11) (i32.const 1128) (i32.const 12) (i32.const 0) (i32.const 9200) (i32.const 32))
    (call $ask (i32.const 12) (i32.const 1144) (i32.const 9) (i32.const 0) (i32.const 9100) (i32.const 16))
    (call $ask (i32.const 13) (i32.const 1160) (i32.const 3) (i32.const 0) (i32.const 0) (i32.const 0))
    (call $ask (i32.const 14) (i32.const 1024) (i32.const 8) (i32.const 255) (i32.const 9300) (i32.const 1)))

  (func (export "_update") (param f32))

  (func (export "_draw") (local $i i32) (local $v i32)
    ;; frame[y * 320 + x] = data[(x / 4) mod 16 + 16 * ((y / 4) mod 16)],
    ;; through the cart's own palette (pal 0: the index modulo 64)
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 76800)))
        (i32.store8 offset=65536 (local.get $i)
          (i32.load8_u offset=8192
            (i32.or
              (i32.and (i32.shr_u (i32.rem_u (local.get $i) (i32.const 320))
                                  (i32.const 2))
                       (i32.const 15))
              (i32.shl
                (i32.and (i32.shr_u (i32.div_u (local.get $i) (i32.const 320))
                                    (i32.const 2))
                         (i32.const 15))
                (i32.const 4)))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))
    (call $blit (i32.const 65536) (i32.const 0))

    ;; the fifteen answers, as bars along the bottom
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 15)))
        (local.set $v (i32.load offset=4096 (i32.shl (local.get $i) (i32.const 2))))
        (call $rect
          (i32.add (i32.const 4) (i32.mul (local.get $i) (i32.const 21)))
          (i32.sub (i32.const 236)
                   (i32.add (i32.and (local.get $v) (i32.const 63)) (i32.const 1)))
          (i32.const 18)
          (i32.add (i32.and (local.get $v) (i32.const 63)) (i32.const 1))
          (i32.add (i32.const 8) (i32.shr_u (local.get $v) (i32.const 6))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))

    ;; the short read's six bytes and the last byte, as colours
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 6)))
        (call $rect (i32.add (i32.const 8) (i32.mul (local.get $i) (i32.const 10)))
                    (i32.const 150) (i32.const 8) (i32.const 8)
                    (i32.load8_u offset=9000 (local.get $i)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))
    (call $rect (i32.const 72) (i32.const 150) (i32.const 8) (i32.const 8)
                (i32.load8_u (i32.const 9300)))

    ;; the subfolder's text, at the length the read answered
    (call $print (i32.const 9200) (i32.load (i32.const 4140)) (i32.const 8)
                 (i32.const 164) (i32.const 7)))
)
