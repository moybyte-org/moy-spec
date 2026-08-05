-- A declared canvas resizes the raster and W/H with it (SPEC.md 1, 3.1).
function _init()
  if W ~= 160 or H ~= 120 then
    error("W,H = " .. W .. "," .. H .. ", expected 160,120")
  end
end

function _update(dt)
  if btnp(4) then end
  quit()
end

function _draw()
  cls(3)
  rectb(0, 0, W, H, 7)
  pix(W - 1, H - 1, 12)
end
