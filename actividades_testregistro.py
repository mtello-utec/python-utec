"""
actividades_testregistro.py — Prueba de conexión (Sesión 1).

Celda de inicio en Colab:
    !curl -sL <URL_RAW_DE_ESTE_ARCHIVO> -o actividades_testregistro.py
    import actividades_testregistro
    actividades_testregistro.iniciar()

Actividad de prueba:
    %%actividad a00
    print('hola utec')
"""
import ast
import copy
import datetime
import html
import io
import json
import re
import sys
import unicodedata

# ===================== CONFIGURACIÓN (la edita el docente) =====================
URL_REGISTRO = "https://script.google.com/macros/s/AKfycbx_VuVpxLvHvNEbhTDlXBtyMgZWTdAFow-lwcWXBdH1GVAnOfitV8r_F4HxPmtJnWNgnw/exec"                 # URL del Apps Script publicado (termina en /exec)
TOKEN = "utec2026mts"       # Debe coincidir con TOKEN en Code.gs
CURSO = "UTEC Python M2 - Prueba de conexion"

# ===============================================================================

ALUMNO = None
ESTADO = {}          # memoria entre actividades (p. ej. nombre de la lista inicial)
VALIDACIONES = {}    # id -> (titulo, funcion)

_IGNORAR = {"In", "Out", "exit", "quit", "get_ipython", "quiz_python", "actividades_testregistro"}

# ----------------------------------------------------------------------------- utilidades
def _norm(t):
    """minúsculas, sin tildes, sin signos de puntuación, espacios simples."""
    t = unicodedata.normalize("NFKD", str(t))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower().replace("-", " ").replace("_", " ")
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _es_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _quito_uno(antes, ahora):
    """True si `ahora` es `antes` con exactamente un elemento menos (orden preservado)."""
    if len(ahora) != len(antes) - 1:
        return None
    for i in range(len(antes)):
        if antes[:i] + antes[i + 1:] == ahora:
            return antes[i]
    return None


def _agrego_uno(antes, ahora):
    """Devuelve (indice, elemento) si `ahora` es `antes` con un elemento más."""
    if len(ahora) != len(antes) + 1:
        return None
    for i in range(len(ahora)):
        if ahora[:i] + ahora[i + 1:] == antes:
            return i, ahora[i]
    return None


class _Tee:
    def __init__(self, orig):
        self.orig, self.buf = orig, io.StringIO()

    def write(self, s):
        self.buf.write(s)
        return self.orig.write(s)

    def flush(self):
        self.orig.flush()

    def __getattr__(self, a):
        return getattr(self.orig, a)


class Ctx:
    """Lo que ve una validación: estado antes/después, código, salida y último valor."""

    def __init__(self, antes, ns, codigo, salida, valor):
        self.antes, self.ns, self.salida, self.valor = antes, ns, salida, valor
        self.codigo = codigo
        self.codigo_limpio = re.sub(r"#.*", "", codigo)

    def get(self, *nombres):
        for n in nombres:
            if n in self.ns:
                return self.ns[n]
        return None

    def cambiadas(self):
        return {k: v for k, v in self.ns.items()
                if not k.startswith("_") and k not in _IGNORAR
                and (k not in self.antes or self.antes[k] != v)
                and not callable(v) and type(v).__name__ != "module"}

    def listas_nuevas(self):
        return [k for k, v in self.cambiadas().items() if isinstance(v, list)]

    def usa(self, patron):
        return re.search(patron, self.codigo_limpio) is not None

    def mostro(self, x):
        """El valor x apareció impreso o fue el resultado de la última línea."""
        if self.valor is not None:
            try:
                if self.valor == x:
                    return True
            except Exception:
                pass
        if _es_num(x):
            return re.search(r"(?<![\d.])" + re.escape(str(x)) + r"(?![\d])", self.salida) is not None
        return str(x) in self.salida or repr(x) in self.salida

    def texto(self):
        extra = "" if self.valor is None else "\n" + str(self.valor)
        return _norm(self.salida + extra)

    def dijo(self, frase):
        return _norm(frase) in self.texto()

    def en_orden(self, elementos):
        t, pos = self.texto(), 0
        for e in elementos:
            i = t.find(_norm(e), pos)
            if i < 0:
                return False
            pos = i + len(_norm(e))
        return True


def validacion(aid, titulo):
    def deco(f):
        VALIDACIONES[aid] = (titulo, f)
        return f
    return deco


# ----------------------------------------------------------------------------- motor
def _snapshot(ns):
    snap = {}
    for k, v in ns.items():
        if k.startswith("_") or k in _IGNORAR:
            continue
        if isinstance(v, (list, tuple, dict, set, str, int, float, bool)):
            try:
                snap[k] = copy.deepcopy(v)
            except Exception:
                pass
    return snap


def _ejecutar(ip, celda):
    """Ejecuta el código del alumno en su namespace; devuelve (salida, valor, error)."""
    codigo = ip.transform_cell(celda)
    tee = _Tee(sys.stdout)
    sys.stdout = tee
    valor, error = None, None
    try:
        arbol = ast.parse(codigo)
        ultimo = None
        if arbol.body and isinstance(arbol.body[-1], ast.Expr):
            ultimo = ast.Expression(arbol.body.pop().value)
        exec(compile(arbol, "<actividad>", "exec"), ip.user_ns)
        if ultimo is not None:
            valor = eval(compile(ultimo, "<actividad>", "eval"), ip.user_ns)
    except Exception as e:  # noqa
        error = e
    finally:
        sys.stdout = tee.orig
    if error is not None:
        ip.showtraceback()
    elif valor is not None:
        from IPython.display import display
        display(valor)
    return tee.buf.getvalue(), valor, error


def _mostrar(aid, titulo, ok, total, fallas, registro):
    from IPython.display import HTML, display
    pct = 0 if total == 0 else ok / total
    if pct == 1:
        color, icono, msg = "#1e8e3e", "✅", "¡Correcto!"
    elif pct > 0:
        color, icono, msg = "#e37400", "⚠️", "Vas bien, revisa:"
    else:
        color, icono, msg = "#d93025", "❌", "Revisa:"
    items = "".join(f"<li>{html.escape(f)}</li>" for f in fallas)
    display(HTML(
        f"<div style='border-left:5px solid {color};padding:8px 12px;margin-top:8px;"
        f"font-family:sans-serif;font-size:14px;background:rgba(127,127,127,.08)'>"
        f"<b>{icono} {aid} · {html.escape(titulo)} — {ok}/{total} ({pct:.0%})</b><br>{msg}"
        f"<ul style='margin:4px 0'>{items}</ul>"
        f"<span style='opacity:.7;font-size:12px'>{html.escape(registro)}</span></div>"))


def _enviar(payload):
    if not URL_REGISTRO:
        return "Modo local: el resultado no se envió (falta configurar URL_REGISTRO)."
    try:
        import requests
        r = requests.post(URL_REGISTRO, data=json.dumps(payload),
                          headers={"Content-Type": "text/plain"}, timeout=10)
        if r.ok:
            return "📤 Resultado registrado."
        return f"No se pudo registrar (HTTP {r.status_code}). Vuelve a ejecutar la celda."
    except Exception as e:  # noqa
        return f"No se pudo registrar ({type(e).__name__}). Revisa tu conexión y vuelve a ejecutar."


def actividad(linea, celda):
    from IPython import get_ipython
    ip = get_ipython()
    aid = linea.strip().lower()
    if aid not in VALIDACIONES:
        print(f"⚠️ No existe la actividad '{aid}'. Disponibles: {', '.join(sorted(VALIDACIONES))}")
        return
    if not ALUMNO:
        print("⚠️ Primero ejecuta la celda de inicio (test_registro.iniciar()).")
        return
    titulo, fn = VALIDACIONES[aid]
    antes = _snapshot(ip.user_ns)
    salida, valor, error = _ejecutar(ip, celda)

    if error is not None:
        ok, total = 0, 1
        fallas = [f"Tu código produjo un error ({type(error).__name__}). Corrígelo y vuelve a ejecutar."]
    else:
        try:
            checks = fn(Ctx(antes, ip.user_ns, celda, salida, valor))
        except Exception as e:  # noqa
            checks = [(False, f"No se pudo validar ({type(e).__name__}: {e}).")]
        total = len(checks)
        ok = sum(1 for c, _ in checks if c)
        fallas = [m for c, m in checks if not c and m]

    registro = _enviar({
        "token": TOKEN, "curso": CURSO, "alumno": ALUMNO, "actividad": aid,
        "titulo": titulo, "puntaje": round(ok / total, 4) if total else 0,
        "aciertos": ok, "total": total, "detalle": " | ".join(fallas),
        "codigo": celda[:5000],
        "fecha": datetime.datetime.now().isoformat(timespec="seconds"),
    })
    _mostrar(aid, titulo, ok, total, fallas, registro)


def iniciar(nombre=None):
    global ALUMNO
    from IPython import get_ipython
    ip = get_ipython()
    while not nombre:
        nombre = input("Escribe tu nombre y apellido: ").strip()
    ALUMNO = re.sub(r"\s+", " ", nombre).strip()
    ip.register_magic_function(actividad, "cell", "actividad")
    print(f"👋 Hola {ALUMNO}. Listo: resuelve cada actividad en su celda (empieza con %%actividad).")


# ============================================================================ ACTIVIDADES
@validacion("a00", "Prueba de conexión: hola utec")
def _(c):
    return [
        (c.usa(r"print\s*\("), "Usa la función print()."),
        (c.dijo("hola utec"), "Imprime exactamente: hola utec"),
    ]
