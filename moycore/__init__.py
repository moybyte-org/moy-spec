"""moycore -- the moy console, as a library.

Everything SPEC.md describes and nothing else: the 320x240 indexed raster, the
64-entry palette, the 8x8 font, the sprite sheet and tilemap, the cart folder,
and the verb table a cart calls. No launcher, no windowing, no editors, no
device drivers -- those are a *host's* business (SPEC.md 0) and deliberately
absent here.

What this is for:

  * A host embeds it. Give it a Canvas, poll your own buttons into an Input,
    hand cart bytes to `load_cart`, and call the verb table from whatever
    language binding you have. The only thing you write is the platform shim.
  * The conformance suite runs against it (conformance/), so "pixel-identical"
    is a thing you can check rather than a thing the README claims.
  * It is the readable answer to "what exactly does `circ` do", which prose
    cannot be and a .wasm blob will not be.

Deliberately NOT here: the Lua VM. moycore is the console; the language binding
is a seam (see `api.make_api`, which returns a plain dict of callables). A host
with a Lua 5.4 VM installs that dict as globals; the conformance raster suite
calls it directly. That split is what lets the same core sit under a
MicroPython host, a C host and a browser.

Portability rules for anything added here: stdlib only, no f-strings, no
dataclasses, no typing, no comprehension-heavy hot paths. This must import on
MicroPython.
"""

from .canvas import Canvas, Image
from .sheet import SpriteSheet, TileMap
from .cart import Cart, load_cart, CartError
from .api import make_api, Input
from . import palette
from . import font

WIDTH = 320
HEIGHT = 240

__all__ = [
    "Canvas", "Image", "SpriteSheet", "TileMap", "Cart", "load_cart",
    "CartError", "make_api", "Input", "palette", "font", "WIDTH", "HEIGHT",
]

__version__ = "0.1.0"
