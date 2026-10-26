"""
actividades_diccionarios.py — Tema 3 · Diccionarios. Validación automática de actividades en Google Colab.

Celda de inicio del notebook:
    !curl -sL https://raw.githubusercontent.com/mtello-utec/python-utec/refs/heads/main/actividades_diccionarios.py -o actividades_diccionarios.py
    import actividades_diccionarios
    actividades_diccionarios.iniciar()

Actividades: t3a01, t3a02, t3a03, t3a04, t3a05, t3a06
Cada una se resuelve en una celda que empieza con:  %%actividad t3a01
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
CURSO = "UTEC Python M2 - Diccionarios"
VERSION = "2026-10-26 v2"
# ===============================================================================

ALUMNO = None
ESTADO = {}          # memoria entre actividades (p. ej. nombre de la lista inicial)
VALIDACIONES = {}    # id -> (titulo, funcion)

_IGNORAR = {"In", "Out", "exit", "quit", "get_ipython", "actividades_diccionarios"}


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
        print("⚠️ Primero ejecuta la celda de inicio (actividades_diccionarios.iniciar()).")
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
    print(f"👋 Hola {ALUMNO}. Listo: resuelve cada actividad en su celda (empieza con %%actividad).  [versión 2026-10-26 v2]")


# ============================================================================ ACTIVIDADES
_COBRE = [
    ("Escondida", "Chile", 1281400, 2023),
    ("Grasberg", "Indonesia", 816466, 2023),
    ("Collahuasi", "Chile", 563390, 2023),
    ("Antamina", "Perú", 434238, 2024),
    ("Cerro Verde", "Perú", 449096, 2024),
    ("Las Bambas", "Perú", 400000, 2021),
]


def _num(x):
    if _es_num(x):
        return x
    try:
        return float(str(x).replace(",", "").strip())
    except ValueError:
        return None


def _claves(d):
    """Diccionario con claves normalizadas ('Ítem' -> 'item')."""
    return {_norm(k): v for k, v in d.items()} if isinstance(d, dict) else {}


def _registros_productos(d):
    """Convierte 'productos' a una lista de registros {item, cantidad, precio}.
    Acepta: {'item': [...], 'cantidad': [...], 'precio': [...]}
            {'arroz': {'cantidad':.., 'precio':..}, ...}
            {1: {'item':.., 'cantidad':.., 'precio':..}, ...}"""
    if not isinstance(d, dict):
        return None
    k = _claves(d)
    if {"item", "cantidad", "precio"} <= set(k):
        cols = [k["item"], k["cantidad"], k["precio"]]
        if all(isinstance(x, (list, tuple)) for x in cols) and len({len(x) for x in cols}) == 1:
            return [{"item": a, "cantidad": b, "precio": p} for a, b, p in zip(*cols)]
        return [{"item": k["item"], "cantidad": k["cantidad"], "precio": k["precio"]}]
    regs = []
    for clave, v in d.items():
        kv = _claves(v)
        if {"cantidad", "precio"} <= set(kv):
            regs.append({"item": kv.get("item", clave), "cantidad": kv["cantidad"], "precio": kv["precio"]})
        else:
            return None
    return regs


@validacion("t3a01", "Diccionario productos")
def _(c):
    d = c.get("productos")
    if not isinstance(d, dict):
        return [(False, "Crea el diccionario con el nombre exacto productos (usa llaves { })."),
                (False, ""), (False, ""), (False, "")]
    regs = _registros_productos(d)
    return [
        (True, ""),
        (regs is not None, "Usa las claves ítem, cantidad y precio. Ejemplo: {'item': [...], 'cantidad': [...], 'precio': [...]}"),
        (regs is not None and len(regs) == 5, f"Debe tener 5 productos (tiene {len(regs) if regs else 0})."),
        (bool(regs) and all(_es_num(r["cantidad"]) and _es_num(r["precio"]) for r in regs),
         "cantidad y precio deben ser números (sin comillas)."),
    ]


@validacion("t3a02", "Último valor del diccionario")
def _(c):
    d = c.get("productos")
    if not isinstance(d, dict) or not d:
        return [(False, "Ejecuta primero la actividad t3a01 (diccionario productos)."), (False, "")]
    ultima = list(d)[-1]
    ultimo = d[ultima]
    return [
        (c.usa(r"productos\s*(\.\s*values\s*\(\s*\)|\.\s*get\s*\(|\[\s*" + re.escape(repr(ultima)).replace("'", "['\"]") + r"\s*\])"),
         f"Accede con list(productos.values())[-1] o con productos[{ultima!r}]."),
        (c.mostro(ultimo), f"Muestra el último valor ({ultimo!r})."),
    ]


@validacion("t3a03", "Pares clave-valor")
def _(c):
    d = c.get("productos")
    if not isinstance(d, dict) or not d:
        return [(False, "Ejecuta primero la actividad t3a01 (diccionario productos)."), (False, "")]
    t = c.texto()
    return [
        (c.usa(r"productos\s*\.\s*items\s*\(\s*\)"), "Usa productos.items() para obtener los pares clave-valor."),
        (all(_norm(k) in t for k in d) or c.mostro(d.items()),
         "Muestra todos los pares en pantalla (con print o recorriéndolos con for)."),
    ]


_DICT_INFO = {"nombre": "david", "apellido": "allende", "edad": 29, "profesion": "ingeniero"}


@validacion("t3a04", "Copia de diccionario")
def _(c):
    d, cp = c.get("dict_info"), c.get("dict_info_copy")
    k = _claves(d)
    if not isinstance(d, dict):
        return [(False, "Crea el diccionario con el nombre exacto dict_info.")] + [(False, "")] * 3
    ok_base = set(k) == set(_DICT_INFO) and all(
        (_norm(k[x]) == _norm(v) if isinstance(v, str) else k[x] == v) for x, v in _DICT_INFO.items()
        if x != "profesion") and _norm(k.get("profesion", "")) == "ingeniero"
    if not isinstance(cp, dict):
        return [(ok_base, "dict_info debe tener nombre='david', apellido='allende', edad=29, profesion='ingeniero'."),
                (False, "Crea la copia con dict_info_copy = dict_info.copy()."), (False, ""), (False, "")]
    kc = _claves(cp)
    return [
        (ok_base, "dict_info debe conservar: nombre='david', apellido='allende', edad=29, profesion='ingeniero'."),
        (cp is not d and c.usa(r"dict_info_copy\s*=\s*(dict_info\s*\.\s*copy\s*\(\s*\)|dict\s*\(\s*dict_info\s*\)|copy\s*\.\s*(deep)?copy\s*\(\s*dict_info\s*\))"),
         "Crea una copia real con dict_info.copy(). Con dict_info_copy = dict_info ambos nombres apuntan al mismo diccionario."),
        ("profesion" in kc and _norm(kc["profesion"]) != "ingeniero", "Cambia la profesión en dict_info_copy."),
        (all(kc.get(x) == k.get(x) for x in k if x != "profesion"), "En la copia solo debe cambiar la profesión."),
    ]


def _filas_dict_cobre(d):
    """Normaliza dict_cobre a filas (mina, pais, prod, periodo).
    Acepta: por columnas {'Mina': [...], 'Pais': [...], ...}
            por mina {'Escondida': {'pais':.., 'produccion':.., 'periodo':..}} o {'Escondida': ('Chile', 1281400, 2023)}"""
    if not isinstance(d, dict):
        return None
    k = _claves(d)
    cols = [k.get(x) for x in ("mina", "pais", "produccion", "periodo")]
    if all(isinstance(x, (list, tuple)) for x in cols):
        return list(zip(*cols))
    filas = []
    for mina, v in d.items():
        if isinstance(v, dict):
            kv = _claves(v)
            filas.append((kv.get("mina", mina), kv.get("pais"), kv.get("produccion"), kv.get("periodo")))
        elif isinstance(v, (list, tuple)) and len(v) == 3:
            filas.append((mina,) + tuple(v))
        else:
            return None
    return filas


@validacion("t3a05", "Diccionario dict_cobre")
def _(c):
    d = c.get("dict_cobre")
    if not isinstance(d, dict):
        return [(False, "Crea el diccionario con el nombre exacto dict_cobre (usa llaves { }).")] + [(False, "")] * 3
    filas = _filas_dict_cobre(d)
    if filas is None:
        return [(True, ""), (False, "Organízalo por columnas {'Mina': [...], 'Pais': [...], 'Produccion': [...], 'Periodo': [...]} "
                                   "o por mina {'Escondida': {'pais': ..., 'produccion': ..., 'periodo': ...}}."),
                (False, ""), (False, "")]
    por_mina = {_norm(f[0]): f for f in filas}
    faltan = [m for m, *_ in _COBRE if _norm(m) not in por_mina]
    valores = not faltan and all(
        _norm(por_mina[_norm(m)][1]) == _norm(p) and _num(por_mina[_norm(m)][2]) == pr and _num(por_mina[_norm(m)][3]) == pe
        for m, p, pr, pe in _COBRE)
    numeros = not faltan and all(_es_num(por_mina[_norm(m)][2]) and _es_num(por_mina[_norm(m)][3]) for m, *_ in _COBRE)
    return [
        (True, ""),
        (not faltan, f"Faltan minas: {', '.join(faltan)}."),
        (valores, "Revisa los datos: país, producción y periodo deben coincidir con la tabla."),
        (numeros, "Producción y periodo deben ser números sin comillas ni comas (1281400, no '1,281,400')."),
    ]


_ESTUDIANTES = ["ana", "luis", "carlos"]


@validacion("t3a06", "Promedio de notas")
def _(c):
    d = c.get("notas_est")
    k = _claves(d)
    if not isinstance(d, dict):
        return [(False, "Crea el diccionario con el nombre exacto notas_est.")] + [(False, "")] * 3
    notas_ok = all(isinstance(k.get(e), (list, tuple)) and len(k[e]) == 4 and all(_es_num(n) for n in k[e])
                   for e in _ESTUDIANTES)
    numeros = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", c.salida + ("" if c.valor is None else str(c.valor)))]
    faltan = []
    for e in _ESTUDIANTES:
        if not notas_ok:
            break
        prom = sum(k[e]) / 4
        if not (re.search(rf"\b{e}\b", c.texto()) and any(abs(n - prom) <= 0.051 for n in numeros)):
            faltan.append(e.capitalize())
    return [
        (set(_ESTUDIANTES) <= set(k), "Las claves deben ser 'Ana', 'Luis' y 'Carlos'."),
        (notas_ok, "Asigna a cada estudiante una lista con 4 notas numéricas."),
        (c.usa(r"\bsum\s*\(|\bmean\s*\(|/\s*len\s*\(|/\s*4\b"), "Calcula el promedio con código (por ejemplo sum(notas) / len(notas))."),
        (notas_ok and not faltan, "Imprime el promedio de cada estudiante junto a su nombre"
         + (f" (falta: {', '.join(faltan)})." if faltan else ".")),
    ]
