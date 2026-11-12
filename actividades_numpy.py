"""
actividades_numpy.py — Tema 4 · NumPy. Validación automática de actividades en Google Colab.

Celda de inicio del notebook:
    !curl -sL https://raw.githubusercontent.com/mtello-utec/python-utec/refs/heads/main/actividades_numpy.py -o actividades_numpy.py
    import actividades_numpy
    actividades_numpy.iniciar()

Actividades: t4a01, t4a02, t4a03, t4a04, t4a05
Cada una se resuelve en una celda que empieza con:  %%actividad t4a01
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
CURSO = "UTEC Python M2 - NumPy"
VERSION = "2026-11-12 v4"
# ===============================================================================

ALUMNO = None
ESTADO = {}          # memoria entre actividades (p. ej. nombre de la lista inicial)
VALIDACIONES = {}    # id -> (titulo, funcion)

_IGNORAR = {"In", "Out", "exit", "quit", "get_ipython", "actividades_numpy"}


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

    def asignadas(self):
        """Variables a las que el código de la celda asigna un valor (aunque ya existieran)."""
        nombres = []
        try:
            for nodo in ast.walk(ast.parse(self.codigo)):
                if isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Store) and nodo.id not in nombres:
                    nombres.append(nodo.id)
        except SyntaxError:
            pass
        return {n: self.ns[n] for n in nombres if n in self.ns}

    def listas_nuevas(self):
        nombres = [k for k, v in self.asignadas().items() if isinstance(v, list)]
        return nombres + [k for k, v in self.cambiadas().items() if isinstance(v, list) and k not in nombres]

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
        print("⚠️ Primero ejecuta la celda de inicio (actividades_numpy.iniciar()).")
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
    print(f"👋 Hola {ALUMNO}. Listo: resuelve cada actividad en su celda (empieza con %%actividad).  [versión 2026-11-12 v4]")


# ============================================================================ ACTIVIDADES
import numpy as np

_DATA = np.array([[35, 10, 1, 3500, 12000],
                  [50, 25, 3, 6000, 30000],
                  [23,  2, 0,   50,  1500],
                  [42, 15, 2, 1000,  2800]])
_A = np.array([[1, 2, 3], [3, 2, 1]])
_B = np.array([[0, 2], [1, -1], [0, 1]])


def _texto_crudo(c):
    return c.salida + ("" if c.valor is None else "\n" + str(c.valor))


def _nums(c):
    """Todos los números que aparecen en la salida (incluye notación científica de NumPy)."""
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", _texto_crudo(c).replace(",", ""))]


def _sin_data(nums):
    """Quita de la salida el data_array impreso completo, para que no cuente como respuesta."""
    seq = [float(x) for x in _DATA.ravel()]
    for i in range(len(nums) - len(seq) + 1):
        if all(abs(a - b) < 1e-9 for a, b in zip(nums[i:i + len(seq)], seq)):
            return nums[:i] + nums[i + len(seq):]
    return nums


def _contiene(nums, valores, tol=0.06):
    """Cada valor esperado aparece en la salida (en orden)."""
    i = 0
    for v in valores:
        while i < len(nums) and abs(nums[i] - v) > tol:
            i += 1
        if i == len(nums):
            return False
        i += 1
    return True


def _arr_mostrado(c, esperado):
    """El arreglo se imprimió, fue el resultado de la última línea o quedó guardado en una variable."""
    if isinstance(c.valor, np.ndarray) and c.valor.shape == esperado.shape and np.allclose(c.valor, esperado):
        return True
    if any(isinstance(v, np.ndarray) and v.shape == esperado.shape and np.allclose(v, esperado)
           for v in c.asignadas().values()):
        return True
    return _contiene(_sin_data(_nums(c)), [float(x) for x in esperado.ravel()])


def _data(c):
    d = c.get("data_array")
    return d if isinstance(d, np.ndarray) and d.shape == _DATA.shape and np.allclose(d, _DATA) else None


@validacion("t4a01", "Crear data_array")
def _(c):
    d = c.get("data_array")
    if not isinstance(d, np.ndarray):
        msg = ("data_array es una lista: conviértela con np.array(...)." if isinstance(d, list)
               else "Crea el arreglo con el nombre exacto data_array.")
        return [(False, msg), (False, ""), (False, "")]
    return [
        (c.usa(r"np\s*\.\s*array\s*\("), "Crea el arreglo con np.array(...)."),
        (d.shape == (4, 5), f"data_array tiene forma {d.shape}; debe ser (4, 5): 4 registros y 5 variables."),
        (d.shape == (4, 5) and np.allclose(d, _DATA), "Revisa los valores: deben coincidir con la tabla, fila por fila."),
    ]


@validacion("t4a02", "Atributos de data_array")
def _(c):
    if _data(c) is None:
        return [(False, "Ejecuta primero la actividad t4a01 (data_array)."), (False, ""), (False, "")]
    t = _texto_crudo(c)
    nums = _nums(c)
    return [
        (c.usa(r"data_array\s*\.\s*ndim\b") and 2 in nums, "Muestra el número de dimensiones con data_array.ndim."),
        (c.usa(r"data_array\s*\.\s*shape\b") and "(4, 5)" in t, "Muestra el tamaño de cada dimensión con data_array.shape."),
        (c.usa(r"data_array\s*\.\s*size\b") and 20 in nums, "Muestra el número de elementos con data_array.size."),
    ]


@validacion("t4a03", "Multiplicación de matrices")
def _(c):
    A, B = c.get("A"), c.get("B")
    a_ok = isinstance(A, np.ndarray) and A.shape == _A.shape and np.array_equal(A, _A)
    b_ok = isinstance(B, np.ndarray) and B.shape == _B.shape and np.array_equal(B, _B)
    return [
        (a_ok, "Crea A = np.array([[1, 2, 3], [3, 2, 1]])  (2×3)."),
        (b_ok, "Crea B = np.array([[0, 2], [1, -1], [0, 1]])  (3×2)."),
        (c.usa(r"np\s*\.\s*(dot|matmul)\s*\(|\.\s*dot\s*\(|@"),
         "Usa np.dot(A, B) (o A @ B). Con * se multiplica elemento a elemento, no es producto de matrices."),
        (a_ok and b_ok and _arr_mostrado(c, _A @ _B), "Muestra el resultado de A·B (una matriz 2×2)."),
        (a_ok and b_ok and _arr_mostrado(c, _B @ _A), "Muestra el resultado de B·A (una matriz 3×3)."),
    ]


@validacion("t4a04", "Selección de elementos")
def _(c):
    if _data(c) is None:
        return [(False, "Ejecuta primero la actividad t4a01 (data_array)."), (False, "")]
    return [
        (c.usa(r"data_array\s*\[[^\]]*,"), "Selecciona con [filas, columnas], por ejemplo data_array[1:3, 3:5]."),
        (_arr_mostrado(c, _DATA[1:3, 3:5]),
         "Muestra Impuestos e Ingresos del 2.º y 3.er registro: [[6000 30000] [50 1500]]."),
    ]


@validacion("t4a05", "Estadísticas por variable")
def _(c):
    if _data(c) is None:
        return [(False, "Ejecuta primero la actividad t4a01 (data_array).")] + [(False, "")] * 3
    nums = _sin_data(_nums(c))
    return [
        (c.usa(r"axis\s*=\s*0|\.\s*(min|max|mean)\s*\(\s*0\s*\)|\bfor\b"),
         "Calcula por columna con axis=0, por ejemplo data_array.min(axis=0)."),
        (_contiene(nums, _DATA.min(axis=0)), "Muestra el mínimo de cada variable (5 valores)."),
        (_contiene(nums, _DATA.max(axis=0)), "Muestra el máximo de cada variable (5 valores)."),
        (_contiene(nums, _DATA.mean(axis=0)), "Muestra el promedio de cada variable (5 valores)."),
    ]
