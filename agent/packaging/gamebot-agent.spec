# PyInstaller spec: `uv run --with pyinstaller pyinstaller packaging/gamebot-agent.spec --distpath dist --workpath build`
from pathlib import Path

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root / "src")],
    hiddenimports=["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
                   "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="gamebot-agent", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="gamebot-agent")
