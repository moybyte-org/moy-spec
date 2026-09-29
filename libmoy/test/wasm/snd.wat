;; snd, driven by the harness (wasm_test.c) one _update at a time: it offers
;; pmem[0] frames from pmem[2] (0 means the ramp at 1024) and reports the
;; answer in pmem[1]. _init writes the ramp: frame i is 8i, 4096 frames.
(module
  (import "moy" "snd" (func $snd (param i32 i32) (result i32)))
  (import "moy" "pmem" (func $pmem (param i32 i32 i32) (result i32)))

  (memory (export "memory") 1 1)

  (func (export "_init") (local $i i32)
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 4096)))
        (i32.store16 offset=1024 (i32.shl (local.get $i) (i32.const 1))
                     (i32.shl (local.get $i) (i32.const 3)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each))))

  (func (export "_update") (param f32) (local $p i32)
    (local.set $p (call $pmem (i32.const 2) (i32.const 0) (i32.const 0)))
    (if (i32.eqz (local.get $p)) (then (local.set $p (i32.const 1024))))
    (drop (call $pmem (i32.const 1)
      (call $snd (local.get $p)
                 (call $pmem (i32.const 0) (i32.const 0) (i32.const 0)))
      (i32.const 1))))

  (func (export "_draw"))
)
