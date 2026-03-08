#!/usr/bin/env python3
"""
aicli TUI diagnostic — run this FIRST before copying any tui.py
It tells you exactly what Textual version you have and what works.

Usage:
    python3 tui_diag.py
"""

import sys

print("=" * 60)
print("aicli TUI Diagnostic")
print("=" * 60)

# 1. Python version
print(f"\n[1] Python: {sys.version}")

# 2. Textual version
try:
    import textual
    ver = textual.__version__
    print(f"[2] Textual: {ver}")
    parts = ver.split(".")
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) > 1 else 0
    
    if major >= 8:
        print("    ⚠  VERSION TOO NEW — Textual 8.x has breaking changes")
        print("    FIX: pip install 'textual==0.89.0'")
    elif major >= 1:
        print("    ⚠  VERSION TOO NEW — Textual 1.x–7.x may have issues")
        print("    FIX: pip install 'textual==0.89.0'")
    else:
        print(f"    ✓ Version OK (0.x series)")
except ImportError:
    print("[2] Textual: NOT INSTALLED")
    print("    FIX: pip install 'textual==0.89.0'")
    sys.exit(1)

# 3. Check TextArea.theme parameter
print("\n[3] TextArea theme='css' support:")
try:
    from textual.widgets import TextArea
    import inspect
    sig = inspect.signature(TextArea.__init__)
    params = list(sig.parameters.keys())
    print(f"    TextArea.__init__ params: {params}")
    if "theme" in params:
        print("    ✓ theme param exists")
    else:
        print("    ✗ theme param MISSING — CSS colors won't apply to TextArea")
except Exception as e:
    print(f"    ✗ Error: {e}")

# 4. Check copy_to_clipboard
print("\n[4] App.copy_to_clipboard:")
try:
    from textual.app import App
    if hasattr(App, "copy_to_clipboard"):
        print("    ✓ copy_to_clipboard exists")
    else:
        print("    ✗ copy_to_clipboard MISSING — Ctrl+Y copy won't work")
        print("    Will fall back to /tmp/aicli_copy.txt")
except Exception as e:
    print(f"    ✗ Error: {e}")

# 5. Check push_screen
print("\n[5] App.push_screen (for Help/Settings overlays):")
try:
    from textual.app import App
    if hasattr(App, "push_screen"):
        print("    ✓ push_screen exists")
    else:
        print("    ✗ push_screen MISSING — Help and Settings screens won't work")
except Exception as e:
    print(f"    ✗ Error: {e}")

# 6. Check Screen import
print("\n[6] textual.screen.Screen:")
try:
    from textual.screen import Screen
    print("    ✓ Screen importable")
except ImportError:
    try:
        from textual.app import Screen
        print("    ✓ Screen importable from textual.app")
    except ImportError:
        print("    ✗ Screen NOT importable — Help/Settings screens will crash on import")

# 7. Quick render test — does a minimal app compose without crashing?
print("\n[7] Minimal render test:")
try:
    import asyncio
    from textual.app import App, ComposeResult
    from textual.widgets import Static, Label
    from textual.containers import Vertical

    class DiagApp(App):
        CSS = """
        Screen { background: #1a1b26; }
        #box { background: #16213e; color: #7aa2f7; height: 3; }
        """
        async def on_mount(self):
            await asyncio.sleep(0.1)
            self.exit(0)
        def compose(self) -> ComposeResult:
            with Vertical(id="box"):
                yield Label("  diagnostic OK")

    async def run_diag():
        app = DiagApp()
        await app.run_async()

    asyncio.run(run_diag())
    print("    ✓ Minimal app ran OK")
except Exception as e:
    print(f"    ✗ Minimal app FAILED: {e}")
    print("    This is why the TUI looks broken — fix Textual version first")

# 8. Check Binding priority= param (added in newer versions)
print("\n[8] Binding priority param:")
try:
    from textual.binding import Binding
    import inspect
    sig = inspect.signature(Binding.__init__)
    params = list(sig.parameters.keys())
    print(f"    Binding params: {params}")
    if "priority" in params:
        print("    ✓ priority param exists — can force-override Ctrl+P etc.")
    else:
        print("    ✗ priority param MISSING — some keys may be captured by Textual")
except Exception as e:
    print(f"    ✗ Error: {e}")

# 9. Which ctrl keys are reserved by Textual
print("\n[9] Keys that Textual 0.89 reserves internally:")
print("    ctrl+p  — command palette (cannot override without priority=True)")
print("    ctrl+c  — copy selection in TextArea / exit")  
print("    ctrl+z  — undo in TextArea")
print("    ctrl+a  — select all in TextArea")
print("    ctrl+v  — paste in TextArea")
print("    Enter   — can be bound at App level but TextArea/Input catch it first")
print("    NOTE: When Input has focus, almost all ctrl+ keys go to the INPUT,")
print("    not the App. To fire App bindings, the Input must NOT have focus,")
print("    OR the binding must be set with priority=True.")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

try:
    major = int(textual.__version__.split(".")[0])
    if major >= 1:
        print("""
⚠  ACTION REQUIRED:
   Your Textual is too new. Run this to fix it:

   pip install 'textual==0.89.0'
   
   (or inside your venv):
   pip install 'textual==0.89.0' --break-system-packages

   Then re-run:  aicli tui
""")
    else:
        print("""
✓  Textual version is OK.

KEY INSIGHT — why shortcuts feel broken:
   When you're typing in the Input box, Textual routes ALL key events
   to the Input first. To use Ctrl+W, Ctrl+E etc., the focus must be
   on the App, not the input.
   
   WORKAROUND: Press Escape or click outside the input box first,
   THEN press your shortcut key. Or use priority=True on bindings.

Copy text: 
   TextArea lets you select text with mouse. Press Ctrl+Y to copy 
   the last focused message. Or use your terminal's own copy 
   (highlight + right-click or Shift+click depending on terminal).
""")
except:
    pass
