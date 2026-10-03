;; write (SPEC.md 16.12, "Writable files"): the cart's own files, written,
;; erased and listed, over a store that outlives the run. The scene runs twice
;; on one store, and _init tells the runs apart by whether saves/slot1.sav has
;; been written: `write` is the first run's frame, `write_again` the second's.
;;
;; The manifest declares "saves/" and "options.cfg" writable, and the cart
;; ships options.cfg ("volume=5"), readme.txt and saves/slot0.sav ("SHIPPED0").
;; What the scene holds a host to:
;;
;;   - a written copy is what read answers, and the shipped file comes back
;;     once it is erased;
;;   - write answers -1 for a path not declared (readme.txt, the folder saves
;;     itself, "Saves/X.sav" in another case), for one the path rule refuses,
;;     and for one past 64 bytes; -2 past 1 MiB; 0 for a 64-byte path, an
;;     empty file, and a path two folders deep;
;;   - erase answers -1 with nothing to erase or a path not writable;
;;   - list is the shipped files and the written ones in bytewise order, each
;;     path once, "Case" and "case" kept apart, a short buffer answering the
;;     whole length, -1 past the end and for a prefix nothing begins with;
;;   - everything written in the first run is there in the second.
;;
;; Each answer is a bar along the bottom, 6 pixels wide on an 8-pixel pitch:
;; for an answer v, u = v + 4, the bar is (u mod 64) + 1 high in colour
;; 8 + (u / 64 mod 32). The listed paths are printed, as many bytes as the
;; 24-byte buffer took, and so is what read answered for options.cfg and
;; saves/slot0.sav; in the second run, the first 64 bytes read back from
;; saves/slot1.sav are cells in their own colours.
;;
;; Memory: the run at 4092, answers at 4096 (four bytes each), listed paths at
;; 5120 (24 bytes each), options.cfg read at 6144, saves/slot0.sav at 6400 and
;; 6416, saves/slot1.sav at 8192, what is written to it at 12288. The 1 MiB +
;; 1 write hands over memory from 0, which is why the memory is 17 pages.
(module
  (import "moy" "read" (func $read (param i32 i32 i32 i32 i32) (result i32)))
  (import "moy" "write" (func $write (param i32 i32 i32 i32) (result i32)))
  (import "moy" "erase" (func $erase (param i32 i32) (result i32)))
  (import "moy" "list" (func $list (param i32 i32 i32 i32 i32) (result i32)))
  (import "moy" "cls" (func $cls (param i32)))
  (import "moy" "rect" (func $rect (param i32 i32 i32 i32 i32)))
  (import "moy" "print" (func $print (param i32 i32 i32 i32 i32)))

  (memory (export "memory") 17 17)
  (data (i32.const 1024) "options.cfg")
  (data (i32.const 1040) "saves/slot1.sav")
  (data (i32.const 1056) "volume=9!")
  (data (i32.const 1072) "readme.txt")
  (data (i32.const 1088) "saves")
  (data (i32.const 1104) "saves/../readme.txt")
  (data (i32.const 1128) "saves//a.sav")
  (data (i32.const 1144) "/options.cfg")
  (data (i32.const 1160) "saves/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
  (data (i32.const 1232) "saves/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
  (data (i32.const 1304) "saves/big.bin")
  (data (i32.const 1320) "saves/slot2.sav")
  (data (i32.const 1336) "saves/sub/deep.sav")
  (data (i32.const 1360) "deep")
  (data (i32.const 1368) "saves/Case.sav")
  (data (i32.const 1384) "saves/case.sav")
  (data (i32.const 1400) "WRITTEN0!")
  (data (i32.const 1416) "saves/slot0.sav")
  (data (i32.const 1432) "saves/tmp.sav")
  (data (i32.const 1448) "saves/")
  (data (i32.const 1456) "saves/x")
  (data (i32.const 1464) "saves/s")
  (data (i32.const 1472) "Saves/X.sav")

  (global $n (mut i32) (i32.const 0))          ;; answers so far

  (func $put (param $v i32)
    (i32.store offset=4096 (i32.shl (global.get $n) (i32.const 2)) (local.get $v))
    (global.set $n (i32.add (global.get $n) (i32.const 1))))

  (func $r (param $p i32) (param $len i32) (param $dst i32) (param $max i32)
    (call $put (call $read (local.get $p) (local.get $len) (i32.const 0)
                           (local.get $dst) (local.get $max))))
  (func $w (param $p i32) (param $len i32) (param $data i32) (param $size i32)
    (call $put (call $write (local.get $p) (local.get $len) (local.get $data)
                            (local.get $size))))
  (func $e (param $p i32) (param $len i32)
    (call $put (call $erase (local.get $p) (local.get $len))))
  (func $l (param $p i32) (param $len i32) (param $i i32) (param $dst i32) (param $max i32)
    (call $put (call $list (local.get $p) (local.get $len) (local.get $i)
                           (local.get $dst) (local.get $max))))

  ;; list "saves/" from index 0 to 7, each path into its 24 bytes at 5120
  (func $listing (local $i i32)
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 8)))
        (call $l (i32.const 1448) (i32.const 6) (local.get $i)
                 (i32.add (i32.const 5120) (i32.mul (local.get $i) (i32.const 24)))
                 (i32.const 24))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each))))

  (func $first
    (local $i i32)
    ;; saves/slot1.sav's bytes: byte i is 7i mod 256
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 300)))
        (i32.store8 offset=12288 (local.get $i) (i32.mul (local.get $i) (i32.const 7)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))
    (call $w (i32.const 1024) (i32.const 11) (i32.const 1056) (i32.const 9))     ;; 2
    (call $r (i32.const 1024) (i32.const 11) (i32.const 6144) (i32.const 32))    ;; 3
    (call $w (i32.const 1072) (i32.const 10) (i32.const 1056) (i32.const 9))     ;; 4
    (call $w (i32.const 1088) (i32.const 5) (i32.const 1056) (i32.const 9))      ;; 5
    (call $w (i32.const 1104) (i32.const 19) (i32.const 1056) (i32.const 9))     ;; 6
    (call $w (i32.const 1128) (i32.const 12) (i32.const 1056) (i32.const 9))     ;; 7
    (call $w (i32.const 1144) (i32.const 12) (i32.const 1056) (i32.const 9))     ;; 8
    (call $w (i32.const 1160) (i32.const 65) (i32.const 1360) (i32.const 4))     ;; 9
    (call $w (i32.const 1232) (i32.const 64) (i32.const 1360) (i32.const 4))     ;; 10
    (call $w (i32.const 1304) (i32.const 13) (i32.const 0) (i32.const 1048577))  ;; 11
    (call $w (i32.const 1040) (i32.const 15) (i32.const 12288) (i32.const 300))  ;; 12
    (call $w (i32.const 1320) (i32.const 15) (i32.const 0) (i32.const 0))        ;; 13
    (call $w (i32.const 1336) (i32.const 18) (i32.const 1360) (i32.const 4))     ;; 14
    (call $w (i32.const 1368) (i32.const 14) (i32.const 1374) (i32.const 1))     ;; 15
    (call $w (i32.const 1384) (i32.const 14) (i32.const 1390) (i32.const 2))     ;; 16
    (call $w (i32.const 1416) (i32.const 15) (i32.const 1400) (i32.const 9))     ;; 17
    (call $w (i32.const 1432) (i32.const 13) (i32.const 1360) (i32.const 1))     ;; 18
    (call $e (i32.const 1432) (i32.const 13))                                    ;; 19
    (call $e (i32.const 1432) (i32.const 13))                                    ;; 20
    (call $e (i32.const 1072) (i32.const 10))                                    ;; 21
    (call $r (i32.const 1432) (i32.const 13) (i32.const 0) (i32.const 0))        ;; 22
    (call $r (i32.const 1320) (i32.const 15) (i32.const 0) (i32.const 0))        ;; 23
    (call $w (i32.const 1472) (i32.const 11) (i32.const 1360) (i32.const 4))     ;; 24
    (call $l (i32.const 1448) (i32.const 6) (i32.const 99) (i32.const 0) (i32.const 0))  ;; 25
    (call $l (i32.const 1456) (i32.const 7) (i32.const 0) (i32.const 0) (i32.const 0))   ;; 26
    (call $l (i32.const 1464) (i32.const 7) (i32.const 3) (i32.const 0) (i32.const 0))   ;; 27
    (call $l (i32.const 1464) (i32.const 7) (i32.const 4) (i32.const 0) (i32.const 0))   ;; 28
    (call $listing)                                                              ;; 29-36
    (call $r (i32.const 1416) (i32.const 15) (i32.const 6400) (i32.const 16)))   ;; 37

  (func $second
    (local $i i32) (local $bad i32)
    (call $r (i32.const 1040) (i32.const 15) (i32.const 8192) (i32.const 300))   ;; 2
    (call $r (i32.const 1024) (i32.const 11) (i32.const 6144) (i32.const 32))    ;; 3
    (call $r (i32.const 1416) (i32.const 15) (i32.const 6400) (i32.const 16))    ;; 4
    (call $e (i32.const 1024) (i32.const 11))                                    ;; 5
    (call $r (i32.const 1024) (i32.const 11) (i32.const 0) (i32.const 0))        ;; 6
    (call $e (i32.const 1416) (i32.const 15))                                    ;; 7
    (call $r (i32.const 1416) (i32.const 15) (i32.const 6416) (i32.const 16))    ;; 8
    (call $e (i32.const 1336) (i32.const 18))                                    ;; 9
    (call $r (i32.const 1336) (i32.const 18) (i32.const 0) (i32.const 0))        ;; 10
    (call $r (i32.const 1368) (i32.const 14) (i32.const 0) (i32.const 0))        ;; 11
    (call $r (i32.const 1384) (i32.const 14) (i32.const 0) (i32.const 0))        ;; 12
    (call $listing)                                                              ;; 13-20
    ;; 21: how many of saves/slot1.sav's bytes are not 7i mod 256
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 300)))
        (if (i32.ne (i32.load8_u offset=8192 (local.get $i))
                    (i32.and (i32.mul (local.get $i) (i32.const 7)) (i32.const 255)))
          (then (local.set $bad (i32.add (local.get $bad) (i32.const 1)))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))
    (call $put (local.get $bad)))

  (func (export "_init")
    (call $r (i32.const 1024) (i32.const 11) (i32.const 0) (i32.const 0))        ;; 0
    (call $r (i32.const 1040) (i32.const 15) (i32.const 0) (i32.const 0))        ;; 1
    (if (i32.load (i32.const 4100))
      (then (i32.store (i32.const 4092) (i32.const 2)) (call $second))
      (else (i32.store (i32.const 4092) (i32.const 1)) (call $first))))

  (func (export "_update") (param f32))

  (func (export "_draw") (local $i i32) (local $u i32) (local $v i32)
    (call $cls (i32.const 1))
    (call $rect (i32.const 300) (i32.const 8) (i32.const 12) (i32.const 12)
                (i32.add (i32.const 10) (i32.load (i32.const 4092))))

    ;; the answers, as bars
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (global.get $n)))
        (local.set $u (i32.add (i32.load offset=4096 (i32.shl (local.get $i) (i32.const 2)))
                               (i32.const 4)))
        (call $rect
          (i32.add (i32.const 4) (i32.mul (local.get $i) (i32.const 8)))
          (i32.sub (i32.const 236) (i32.add (i32.and (local.get $u) (i32.const 63)) (i32.const 1)))
          (i32.const 6)
          (i32.add (i32.and (local.get $u) (i32.const 63)) (i32.const 1))
          (i32.add (i32.const 8) (i32.and (i32.shr_u (local.get $u) (i32.const 6)) (i32.const 31))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))

    ;; the listed paths, as many bytes of each as its buffer took
    (local.set $i (i32.const 0))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 8)))
        (local.set $v (i32.load offset=4096
          (i32.shl (i32.add (local.get $i)
                            (select (i32.const 29) (i32.const 13)
                                    (i32.eq (i32.load (i32.const 4092)) (i32.const 1))))
                   (i32.const 2))))
        (if (i32.ge_s (local.get $v) (i32.const 0))
          (then
            (call $print (i32.add (i32.const 5120) (i32.mul (local.get $i) (i32.const 24)))
                         (select (local.get $v) (i32.const 24) (i32.lt_s (local.get $v) (i32.const 24)))
                         (i32.const 8)
                         (i32.add (i32.const 8) (i32.mul (local.get $i) (i32.const 10)))
                         (i32.const 7))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))

    ;; what read answered for options.cfg and saves/slot0.sav
    (call $print (i32.const 6144) (i32.const 9) (i32.const 8) (i32.const 100) (i32.const 7))
    (call $print (i32.const 6400) (i32.const 9) (i32.const 8) (i32.const 112) (i32.const 7))
    (if (i32.eq (i32.load (i32.const 4092)) (i32.const 2))
      (then
        (call $print (i32.const 6416) (i32.const 8) (i32.const 8) (i32.const 124) (i32.const 7))
        ;; saves/slot1.sav's first 64 bytes, read back
        (local.set $i (i32.const 0))
        (block $done
          (loop $each
            (br_if $done (i32.ge_u (local.get $i) (i32.const 64)))
            (call $rect
              (i32.add (i32.const 8) (i32.mul (i32.rem_u (local.get $i) (i32.const 32)) (i32.const 9)))
              (i32.add (i32.const 140) (i32.mul (i32.div_u (local.get $i) (i32.const 32)) (i32.const 9)))
              (i32.const 8) (i32.const 8)
              (i32.and (i32.load8_u offset=8192 (local.get $i)) (i32.const 63)))
            (local.set $i (i32.add (local.get $i) (i32.const 1)))
            (br $each))))))
)
