pico-8 cartridge // http://www.pico-8.com
version 42
__lua__
-- The FIRST frame. PICO-8 never calls _draw before its first _update, and a
-- cart may rely on that: this one creates the player in _init and only gives
-- it a position in the update, which is the shape dank_tomb has.
function _init()
 player={}
end

function _update60()
 player.pos={x=64,y=64}
end

function _draw()
 cls(1)
 circfill(player.pos.x,player.pos.y,8,7)
end
