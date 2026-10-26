"""
actividades_tuplas.py — Tema 2 · Tuplas. Validación automática de actividades en Google Colab.

Celda de inicio del notebook:
    !curl -sL https://raw.githubusercontent.com/mtello-utec/python-utec/refs/heads/main/actividades_tuplas.py -o actividades_tuplas.py
    import actividades_tuplas
    actividades_tuplas.iniciar()

Actividades: t2a01, t2a02, t2a03, t2a04, t2a05, t2a06
Cada una se resuelve en una celda que empieza con:  %%actividad t2a01
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
CURSO = "UTEC Python M2 - Tuplas"
# ===============================================================================

ALUMNO = None
ESTADO = {}          # memoria entre actividades (p. ej. nombre de la lista inicial)
VALIDACIONES = {}    # id -> (titulo, funcion)

_IGNORAR = {"In", "Out", "exit", "quit", "get_ipython", "actividades_tuplas"}


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
        print("⚠️ Primero ejecuta la celda de inicio (actividades_tuplas.iniciar()).")
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
_COBRE = [
    ("Escondida", "Chile", 1281400, 2023),
    ("Grasberg", "Indonesia", 816466, 2023),
    ("Collahuasi", "Chile", 563390, 2023),
    ("Antamina", "Perú", 434238, 2024),
    ("Cerro Verde", "Perú", 449096, 2024),
    ("Las Bambas", "Perú", 400000, 2021),
]
_MINAS = {_norm(f[0]) for f in _COBRE}


def _num(x):
    """1281400, 1281400.0 o '1,281,400' -> 1281400 (None si no es convertible)."""
    if _es_num(x):
        return x
    try:
        return float(str(x).replace(",", "").strip())
    except ValueError:
        return None


def _filas_cobre(t):
    """Normaliza la tabla de cobre a una lista de filas (mina, pais, prod, periodo).
    Acepta filas (con o sin encabezado) o columnas."""
    if not isinstance(t, (tuple, list)) or not t:
        return None
    if not all(isinstance(f, (tuple, list)) for f in t):
        return None
    filas = [tuple(f) for f in t]
    if len(filas) == 4 and all(len(f) >= 6 for f in filas):         # por columnas
        filas = list(zip(*filas))
    filas = [f for f in filas if f and _norm(f[0]) not in ("mina", "minas")]
    return filas


def _revisar_cobre(filas):
    """Devuelve (tiene_las_6, valores_ok, numeros_ok, faltan)."""
    por_mina = {_norm(f[0]): f for f in filas if len(f) >= 4}
    faltan = [m for m, *_ in _COBRE if _norm(m) not in por_mina]
    valores, numeros = True, True
    for m, p, prod, per in _COBRE:
        f = por_mina.get(_norm(m))
        if f is None:
            valores = False
            continue
        if _norm(f[1]) != _norm(p) or _num(f[2]) != prod or _num(f[3]) != per:
            valores = False
        if not (_es_num(f[2]) and _es_num(f[3])):
            numeros = False
    return not faltan, valores, numeros, faltan


@validacion("t2a01", "Tupla de equipos")
def _(c):
    t = c.get("equipos")
    if not isinstance(t, tuple):
        msg = ("equipos es una lista; las tuplas se crean con paréntesis ( )." if isinstance(t, list)
               else "Crea la tupla con el nombre exacto equipos.")
        return [(False, msg), (False, ""), (False, "")]
    return [
        (True, ""),
        (len(t) == 5 and all(isinstance(x, str) and x.strip() for x in t),
         f"equipos tiene {len(t)} elementos; deben ser 5 equipos (texto)."),
        (c.mostro(t), "Muestra la tupla en pantalla con print(equipos)."),
    ]


@validacion("t2a02", "Tupla info_personal")
def _(c):
    t = c.get("info_personal")
    if not isinstance(t, tuple):
        msg = ("info_personal es una lista; usa paréntesis ( ) para crear una tupla." if isinstance(t, list)
               else "Crea la tupla con el nombre exacto info_personal.")
        return [(False, msg), (False, ""), (False, "")]
    esperado = (2, 2.5, "UTEC", True)
    tipos_ok = len(t) == 4 and [type(x) for x in t] == [int, float, str, bool]
    return [
        (True, ""),
        (len(t) == 4 and tipos_ok and t[0] == 2 and t[1] == 2.5 and _norm(t[2]) == "utec" and t[3] is True,
         "info_personal debe ser (2, 2.5, 'UTEC', True), en ese orden y con esos tipos."),
        (re.search(r"heterog|mixt", _norm(c.codigo + " " + c.salida)) is not None,
         "Responde la pregunta: ¿qué tipo de tupla es? (en un comentario o con print)."),
    ]


@validacion("t2a03", "Último y primeros 3 equipos")
def _(c):
    t = c.get("equipos")
    if not isinstance(t, tuple) or len(t) < 3:
        return [(False, "Ejecuta primero la actividad t2a01 (tupla equipos)."), (False, ""), (False, ""), (False, "")]
    return [
        (c.usa(r"equipos\s*\[\s*(-1|len\s*\(\s*equipos\s*\)\s*-\s*1)\s*\]"), "Accede al último con equipos[-1]."),
        (c.mostro(t[-1]), f"Muestra el último equipo ({t[-1]!r})."),
        (c.usa(r"equipos\s*\[\s*0?\s*:\s*3\s*\]"), "Accede a los primeros 3 con equipos[:3]."),
        (c.mostro(t[:3]), f"Muestra los primeros 3 equipos ({t[:3]}). Usa print() para cada resultado."),
    ]


@validacion("t2a04", "Desempaquetar los 2 últimos")
def _(c):
    t = c.get("equipos")
    if not isinstance(t, tuple) or len(t) < 2:
        return [(False, "Ejecuta primero la actividad t2a01 (tupla equipos)."), (False, ""), (False, "")]
    a, b = c.get("equipo_A"), c.get("equipo_B")
    return [
        (a == t[-2], f"equipo_A debe ser el penúltimo equipo ({t[-2]!r})."),
        (b == t[-1], f"equipo_B debe ser el último equipo ({t[-1]!r})."),
        (c.usa(r"equipo_A\s*,\s*equipo_B\s*\)?\s*=(?!=)"),
         "Desempaqueta en una sola línea: ..., equipo_A, equipo_B = equipos  (o = equipos[-2:])."),
    ]


@validacion("t2a05", "Tupla cobre_prod")
def _(c):
    t = c.get("cobre_prod")
    if not isinstance(t, tuple):
        msg = ("cobre_prod debe ser una tupla (usa paréntesis), no una lista." if isinstance(t, list)
               else "Crea la tupla con el nombre exacto cobre_prod.")
        return [(False, msg)] + [(False, "")] * 3
    filas = _filas_cobre(t)
    if filas is None:
        return [(True, ""), (False, "Cada mina debe ser una tupla: ('Escondida', 'Chile', 1281400, 2023)."),
                (False, ""), (False, "")]
    seis, valores, numeros, faltan = _revisar_cobre(filas)
    return [
        (True, ""),
        (seis, f"Faltan minas: {', '.join(faltan)}."),
        (valores, "Revisa los datos: mina, país, producción y periodo deben coincidir con la tabla."),
        (numeros, "Producción y periodo deben ser números sin comillas ni comas (1281400, no '1,281,400')."),
    ]


def _variantes(n):
    n = _num(n)
    if n is None:
        return []
    n = int(n) if float(n).is_integer() else n
    return [_norm(str(n)), _norm(f"{n:,}"), _norm(f"{n:,}".replace(",", "."))]


@validacion("t2a06", "Enunciados de producción")
def _(c):
    filas = _filas_cobre(c.get("cobre_prod")) or []
    seis, valores, *_ = _revisar_cobre(filas)
    filas = filas if (seis and valores) else _COBRE
    texto = c.texto()
    faltan = []
    for mina, pais, prod, per in filas[:6]:
        ok = any(
            _norm(f"La mina {mina}, ubicada en {pais} tiene una producción anual de") + " " + v + " "
            + _norm(f"toneladas de cobre en el {int(_num(per))}") in texto
            for v in _variantes(prod))
        if not ok:
            faltan.append(str(mina))
    return [
        (c.usa(r"\bcobre_prod\b") and
         c.usa(r"(?m)(\bfor\s*\(?\s*\w+\s*,\s*\w+[^\n]*\bin\b|^\s*\(?\s*\w+\s*,\s*\w+[^\n=]*=(?!=))"),
         "Desempaqueta la tupla, por ejemplo: for mina, pais, prod, periodo in cobre_prod:"),
        (not faltan, f"Faltan o no coinciden los enunciados de: {', '.join(faltan)}." if faltan else ""),
    ]
