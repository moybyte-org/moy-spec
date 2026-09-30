;; snd (SPEC.md 16.9, "Sample audio"): the queue a host holds for
;; the cart's samples. The player protocol stops the clock and plays nothing,
;; so no frame leaves the queue and every answer is exact on every host.
;; _init asks seven questions and _update an eighth, each answer drawn as a
;; bar in _draw. What the scene holds a host to:
;;
;;   - with nframes 0 snd answers the room, 2,048 frames when nothing is
;;     queued, and reads no pointer at all;
;;   - it queues what fits and answers how many, at any alignment;
;;   - a full queue answers 0, and stays full while the clock stands.
;;
;; A bar is 18 pixels wide; its height is (answer mod 64) + 1 and its colour 8
;; + answer / 64, so every answer up to 2,048 draws its own bar.
;;
;; Memory: the samples from 1024 (4,096 bytes, a sawtooth), answers at 8192.
(module
  (import "moy" "snd" (func $snd (param i32 i32) (result i32)))
  (import "moy" "cls" (func $cls (param i32)))
  (import "moy" "rect" (func $rect (param i32 i32 i32 i32 i32)))

  (memory (export "memory") 1 1)

  (func $ask (param $k i32) (param $pcm i32) (param $n i32)
    (i32.store offset=8192 (i32.shl (local.get $k) (i32.const 2))
      (call $snd (local.get $pcm) (local.get $n))))

  (func (export "_init") (local $i i32)
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 2048)))
        (i32.store16 offset=1024 (i32.shl (local.get $i) (i32.const 1))
          (i32.mul (i32.sub (i32.and (local.get $i) (i32.const 63)) (i32.const 32))
                   (i32.const 512)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each)))
    (call $ask (i32.const 0) (i32.const 0) (i32.const 0))
    (call $ask (i32.const 1) (i32.const 1024) (i32.const 300))
    (call $ask (i32.const 2) (i32.const 0) (i32.const 0))
    (call $ask (i32.const 3) (i32.const 1025) (i32.const 2000))
    (call $ask (i32.const 4) (i32.const 0) (i32.const 0))
    (call $ask (i32.const 5) (i32.const 1024) (i32.const 1))
    (call $ask (i32.const 6) (i32.const 0x7ffffff0) (i32.const 0)))

  (func (export "_update") (param f32)
    (call $ask (i32.const 7) (i32.const 0) (i32.const 0)))

  (func (export "_draw") (local $i i32) (local $v i32)
    (call $cls (i32.const 1))
    (block $done
      (loop $each
        (br_if $done (i32.ge_u (local.get $i) (i32.const 8)))
        (local.set $v (i32.load offset=8192 (i32.shl (local.get $i) (i32.const 2))))
        (call $rect
          (i32.add (i32.const 4) (i32.mul (local.get $i) (i32.const 21)))
          (i32.sub (i32.const 236)
                   (i32.add (i32.and (local.get $v) (i32.const 63)) (i32.const 1)))
          (i32.const 18)
          (i32.add (i32.and (local.get $v) (i32.const 63)) (i32.const 1))
          (i32.add (i32.const 8) (i32.shr_u (local.get $v) (i32.const 6))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $each))))
)
