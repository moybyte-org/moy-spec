-- text_bytes -- a moy conformance cart. GENERATED; do not edit.
-- Regenerate with: python3 conformance/build.py
--
-- One static frame replaying a recorded verb trace. Compare the frame
-- your host renders against conformance/golden/text_bytes.png -- SPEC.md 11
-- calls conformance pixel-identical, so any difference is a bug in one
-- of the two implementations and the point is to find out which.
--
-- Bytes outside 0x20-0x7F. NOT part of conformance: SPEC.md 6
-- says "codepoints" where a Lua string is a byte string, and the
-- two readings advance `print` differently. Golden kept ready.

function _draw()
  cls(1)
  print("A\0B", 8, 8, 10)
  print("C\31D", 8, 20, 10)
  print("E\127F", 8, 32, 10)
  print("G\255H", 8, 44, 10)
  print("\0\0\0\0TAIL", 8, 56, 7)
end
