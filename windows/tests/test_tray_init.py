"""AsenaTray.__init__ SIRA invaryantı (AST — Qt/Windows gerektirmez).

refresh()/_busy()'nin OKUduğu her self._x attribute'u, __init__'te _build_menu()/
refresh() ÇAĞRILMADAN ÖNCE atanmış olmalı. Aksi halde ilk refresh() AttributeError
verir. Bu testsiz yakalanmıyordu -> _dns_reload_proc bug'ı (refresh->_busy onu
_build_menu sırasında okurken init geç kalmıştı).
"""
import ast
import pathlib

TRAY = pathlib.Path(__file__).resolve().parent.parent / "asenaplug" / "tray.py"


def _self_attrs(node, ctx):
    return {n.attr for n in ast.walk(node)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "self" and isinstance(n.ctx, ctx)}


def test_init_assigns_busy_refresh_attrs_before_build_menu():
    tree = ast.parse(TRAY.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "AsenaTray")
    methods = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)}

    # __init__: _build_menu()/refresh() çağrısına KADAR atanan self._x'ler
    assigned = set()
    for stmt in methods["__init__"].body:
        dump = ast.dump(stmt)
        if "_build_menu" in dump or "attr='refresh'" in dump:
            break
        assigned |= _self_attrs(stmt, ast.Store)

    # refresh + _busy'nin OKUduğu self._x'ler
    read = _self_attrs(methods["refresh"], ast.Load) | _self_attrs(methods["_busy"], ast.Load)
    built = _self_attrs(methods["_build_menu"], ast.Store)   # menü widget'ları (refresh'ten önce kurulur)
    missing = read - assigned - built - set(methods)          # self.method() çağrıları hariç

    assert not missing, (
        "__init__ şu attribute'ları _build_menu()/refresh()'ten ÖNCE atamıyor "
        f"(ilk refresh AttributeError verir): {sorted(missing)}")
