# PyInstaller spec: the whole CLI as one executable, so "download moy and
# you have the toolchain" is true on machines with no Python. Built by CI for
# Windows, macOS and Linux (.github/workflows/libmoy.yml); reproduce locally
# with `pyinstaller moy.spec`.
#
# The datas are everything moy.py reaches on disk: the web player it serves
# (`run`/`export`), the editor stubs `new` copies, the two normative data
# files moycore reads beside SPEC.md, and the conformance suite's carts,
# goldens and traces so `moy conform` can judge a third-party player from the
# frozen binary alone. Paths inside the bundle mirror the checkout, so no
# module needed a frozen-specific search path. The one thing frozen changes is
# that the player may be OVERRIDDEN: `moy.py::_user_runner` is a per-user data
# dir that wins over the bundled runner/ when it holds a VERSION, which exists
# so somebody building the player themselves can have a release binary serve it
# (`player --build` refuses to run from a frozen binary -- it needs a checkout).

a = Analysis(
    ["moy.py"],
    pathex=["."],
    datas=[
        ("runner", "runner"),
        ("moy-api.lua", "."),
        ("palette.json", "."),
        ("font.bin", "."),
        ("conformance/carts", "conformance/carts"),
        ("conformance/golden", "conformance/golden"),
        ("conformance/traces", "conformance/traces"),
    ],
    hiddenimports=[],
    excludes=["tkinter", "_tkinter"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="moy",
    console=True,
    strip=False,
    upx=False,
)
