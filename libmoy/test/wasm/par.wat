;; par, driven by the harness (wasm_test.c) one _update at a time. _update
;; reads the item count from pmem[0] and the mode from pmem[1], hands par
;; eight 4 KiB stacks from 65536, and writes the stack pointer it has once par
;; returns into pmem[3]. Item i records the stack pointer it was given at
;; 256 + 4i, fills 8 KiB from 131072 + 8192i with (31i + j) mod 256 -- pmem[2]
;; times over, a count _update leaves at 64 because an item reads no global
;; but its stack pointer, so the items last long enough to overlap -- and
;; writes that fill's byte sum plus one at 128 + 4i.
;;
;;   mode 0  every item works
;;   mode 1  item 1 reads past the memory and item 3 reaches unreachable
;;   mode 2  item 2 calls an import
;;   mode 3  a negative count         4  stacks off 16-byte alignment
;;   mode 5  stacks past the memory
(module
  (import "moy" "par" (func $par (param i32 i32 i32 i32)))
  (import "moy" "pmem" (func $pmem (param i32 i32 i32) (result i32)))

  (memory (export "memory") 4 4)
  (global $sp (export "__stack_pointer") (mut i32) (i32.const 1024))

  (func (export "_par") (param $i i32) (param $mode i32)
        (local $j i32) (local $base i32) (local $v i32) (local $sum i32) (local $r i32)
    (i32.store offset=256 (i32.shl (local.get $i) (i32.const 2)) (global.get $sp))
    (if (i32.eq (local.get $mode) (i32.const 1))
      (then
        (if (i32.eq (local.get $i) (i32.const 3)) (then unreachable))
        (if (i32.eq (local.get $i) (i32.const 1))
          (then (drop (i32.load (i32.const -16)))))))
    (if (i32.eq (local.get $mode) (i32.const 2))
      (then
        (if (i32.eq (local.get $i) (i32.const 2))
          (then (drop (call $pmem (i32.const 0) (i32.const 0) (i32.const 0)))))))
    (local.set $base (i32.add (i32.const 131072) (i32.shl (local.get $i) (i32.const 13))))
    (block $rounds_done
      (loop $round
        (br_if $rounds_done (i32.ge_u (local.get $r) (i32.load (i32.const 64))))
        (local.set $j (i32.const 0))
        (local.set $sum (i32.const 0))
        (block $done
          (loop $each
            (br_if $done (i32.ge_u (local.get $j) (i32.const 8192)))
            (local.set $v (i32.and (i32.add (i32.mul (local.get $i) (i32.const 31))
                                            (local.get $j))
                                   (i32.const 255)))
            (i32.store8 (i32.add (local.get $base) (local.get $j)) (local.get $v))
            (local.set $sum (i32.add (local.get $sum) (local.get $v)))
            (local.set $j (i32.add (local.get $j) (i32.const 1)))
            (br $each)))
        (local.set $r (i32.add (local.get $r) (i32.const 1)))
        (br $round)))
    (i32.store offset=128 (i32.shl (local.get $i) (i32.const 2))
               (i32.add (local.get $sum) (i32.const 1))))

  (func (export "_init"))

  (func (export "_update") (param f32) (local $n i32) (local $mode i32) (local $stacks i32)
    (local.set $n (call $pmem (i32.const 0) (i32.const 0) (i32.const 0)))
    (local.set $mode (call $pmem (i32.const 1) (i32.const 0) (i32.const 0)))
    (local.set $stacks (i32.const 65536))
    (i32.store (i32.const 64) (call $pmem (i32.const 2) (i32.const 0) (i32.const 0)))
    (if (i32.eq (local.get $mode) (i32.const 3)) (then (local.set $n (i32.const -1))))
    (if (i32.eq (local.get $mode) (i32.const 4)) (then (local.set $stacks (i32.const 65544))))
    (if (i32.eq (local.get $mode) (i32.const 5)) (then (local.set $stacks (i32.const 245760))))
    (call $par (local.get $n) (local.get $mode) (local.get $stacks) (i32.const 4096))
    (drop (call $pmem (i32.const 3) (global.get $sp) (i32.const 1))))

  (func (export "_draw"))
)
