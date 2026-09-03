pico-8 cartridge // http://www.pico-8.com
version 42
__lua__
-- No update function at all: PICO-8 draws every frame, with nothing to wait
-- for, and so must the port.
function _draw()
 rectfill(0,0,127,127,7)
end
