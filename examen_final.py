"""
examen_final.py — Examen final · UTEC Python Módulo 2.

Celda de inicio del notebook:
    !curl -sL https://raw.githubusercontent.com/mtello-utec/python-utec/refs/heads/main/examen_final.py -o examen_final.py
    import importlib, examen_final
    importlib.reload(examen_final)
    examen_final.iniciar()

Cada respuesta va en una celda que empieza con:  %%examen p01   (p01 … p10)
Una pregunta puede tener varias celdas (p03, p04, p05): todas empiezan con el mismo %%examen pXX.
Se registra la mejor nota de cada pregunta.
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
URL_REGISTRO = "https://script.google.com/macros/s/AKfycbx_VuVpxLvHvNEbhTDlXBtyMgZWTdAFow-lwcWXBdH1GVAnOfitV8r_F4HxPmtJnWNgnw/exec"
TOKEN = "utec2026mts"
CURSO = "UTEC Python M2 - Examen Final"
VERSION = "2026-11-26 examen v1"
MOSTRAR_PISTAS = False   # True: el alumno ve qué corregir; False: solo ve su puntaje
# ===============================================================================

ALUMNO = None
ESTADO = {}          # memoria entre actividades (p. ej. nombre de la lista inicial)
VALIDACIONES = {}    # id -> (titulo, funcion)

_IGNORAR = {"In", "Out", "exit", "quit", "get_ipython", "examen_final"}


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
    if not MOSTRAR_PISTAS and fallas:
        msg = "Revisa tu respuesta: hay criterios que aún no se cumplen." if pct < 1 else msg
        fallas = []
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


def examen(linea, celda):
    from IPython import get_ipython
    ip = get_ipython()
    aid = linea.strip().lower()
    if aid not in VALIDACIONES:
        print(f"⚠️ No existe la pregunta '{aid}'. Disponibles: {', '.join(sorted(VALIDACIONES))}")
        return
    if not ALUMNO:
        print("⚠️ Primero ejecuta la celda de inicio (examen_final.iniciar()).")
        return
    titulo, fn = VALIDACIONES[aid]
    antes = _snapshot(ip.user_ns)
    salida, valor, error = _ejecutar(ip, celda)

    if error is not None:
        ok, total = 0, 1
        if isinstance(error, FileNotFoundError):
            fallas = [f"No se encontró el archivo '{getattr(error, 'filename', '')}'. Súbelo a Colab (panel 📁 Archivos) "
                      "y revisa que el nombre coincida exactamente."]
        else:
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
    ip.register_magic_function(examen, "cell", "examen")
    print(f"👋 Hola {ALUMNO}. Listo: resuelve cada pregunta en su celda (empieza con %%examen).  [versión {VERSION}]")


# ============================================================================ PREGUNTAS
import numpy as np
import pandas as pd

ARCHIVO = "resultados.csv"

_TEMAS = ("Listas", "Tuplas", "Diccionarios", "Numpy", "Pandas")


# ----------------------------------------------------------------------------- utilidades
def _clave(texto):
    return _norm(texto).replace(" ", "")


def _col(df, nombre):
    if not isinstance(df, pd.DataFrame):
        return None
    for c in df.columns:
        if _clave(c) == _clave(nombre):
            return c
    return None


def _texto_crudo(c):
    return c.salida + ("" if c.valor is None else "\n" + str(c.valor))


def _nums(c):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", _texto_crudo(c).replace(",", ""))]


def _aparece(nums, valor, tol):
    return any(abs(n - valor) <= tol for n in nums)


def _actividades(c):
    a = c.get("actividades")
    return a if isinstance(a, dict) else None


def _total_actividades(c):
    a = _actividades(c)
    return sum(len(v) for v in a.values()) if a else None


def _referencia():
    """resultados.csv leído por el validador (no depende de lo que haga el alumno)."""
    try:
        ref = pd.read_csv(ARCHIVO)
    except Exception:
        return None
    return ref


def _candidatos(c, tipos=(pd.DataFrame, pd.Series)):
    objs = list(c.asignadas().values()) + [c.valor]
    return [o for o in objs if isinstance(o, tipos)]


def _como_dict(obj):
    """Series o DataFrame de conteos/porcentajes -> {(claves...): valor}, aceptando formato ancho (unstack)."""
    if isinstance(obj, pd.DataFrame):
        num = obj.select_dtypes("number")
        if num.shape[1] == 0:
            return {}
        if num.shape[1] == 1:
            obj = num.iloc[:, 0]
        else:
            obj = num.stack()
    out = {}
    for k, v in obj.items():
        if pd.isna(v) or v == 0:
            continue
        clave = tuple(sorted(str(x) for x in (k if isinstance(k, tuple) else (k,))))
        out[clave] = float(v)
    return out


def _coincide(obj, esperado, escalas=(1,)):
    d = _como_dict(obj)
    if set(d) != set(esperado):
        return False
    return any(all(abs(d[k] - esperado[k] * e) <= 1e-6 + 0.0051 * e for k in esperado) for e in escalas)


# ============================================================================ pregunta 01
@validacion("p01", "Tupla temas")
def _(c):
    t = c.get("temas")
    if not isinstance(t, tuple):
        msg = ("temas es una lista: usa paréntesis ( ) para crear una tupla." if isinstance(t, list)
               else "Crea la tupla con el nombre exacto temas.")
        return [(False, msg), (False, "")]
    return [
        (True, ""),
        ([_norm(x) for x in t] == [_norm(x) for x in _TEMAS],
         "temas debe contener, en orden: Listas, Tuplas, Diccionarios, Numpy, Pandas."),
    ]


# ============================================================================ pregunta 02
@validacion("p02", "Lista sesiones")
def _(c):
    s = c.get("sesiones")
    if not isinstance(s, list):
        return [(False, "Crea la lista con el nombre exacto sesiones (usa corchetes [ ])."), (False, "")]
    esperado = [f"sesion {i:02d}" for i in range(1, 10)]
    return [
        (True, ""),
        ([_norm(x) for x in s] == esperado, "sesiones debe contener 'Sesion 01', 'Sesion 02', …, 'Sesion 09'."),
    ]


# ============================================================================ pregunta 03
@validacion("p03", "Lista alumnos con range y for")
def _(c):
    a = c.get("alumnos")
    if not isinstance(a, list):
        return [(False, "Crea la lista con el nombre exacto alumnos.")] + [(False, "")] * 3
    return [
        (c.usa(r"\brange\s*\(") and c.usa(r"\bfor\b"), "Genera los elementos con range y for (no los escribas uno a uno)."),
        (a[:9] == [f"alumno{i:02d}" for i in range(1, 10)],
         "Los primeros 9 elementos deben ser 'alumno01' … 'alumno09' (con dos dígitos)."),
        (a[9:] == [f"alumno{i:02d}" for i in range(10, 17)], "Agrega 'alumno10' … 'alumno16' al final de la lista."),
        (len(a) == 16, f"alumnos tiene {len(a)} elementos; al final deben ser 16."),
    ]


# ============================================================================ pregunta 04
@validacion("p04", "Actividades por tema")
def _(c):
    a = _actividades(c)
    if a is None:
        return [(False, "Ejecuta la celda que define el diccionario actividades.")] + [(False, "")] * 4
    vistos = ESTADO.setdefault("p04", set())
    nums = _nums(c)
    for tema in re.findall(r"actividades\s*\[\s*['\"]([^'\"]+)['\"]\s*\]", c.codigo_limpio):
        if tema in a and c.usa(r"len\s*\(\s*actividades\s*\[\s*['\"]" + re.escape(tema)) and len(a[tema]) in nums:
            vistos.add(tema)
    return [(t in vistos, f"Falta mostrar cuántas actividades tiene {t} (usa len(actividades['{t}']))." )
            for t in _TEMAS]


# ============================================================================ pregunta 05
@validacion("p05", "Importar resultados")
def _(c):
    r = c.get("resultados")
    ref = _referencia()
    if not isinstance(r, pd.DataFrame):
        return [(c.usa(r"read_csv\s*\(\s*['\"]resultados\.csv['\"]"), "Importa con pd.read_csv('resultados.csv')."),
                (False, "Guárdalo con el nombre exacto resultados."), (False, "")]
    part = _col(r, "Participacion")
    return [
        (True, ""),
        (ref is None or len(r) == len(ref), "resultados debe tener todos los registros del archivo."),
        (part is not None and (pd.to_numeric(r[part], errors="coerce") == 1).all(),
         "Crea la columna Participacion con valor 1: resultados['Participacion'] = 1."),
    ]


# ============================================================================ pregunta 06
@validacion("p06", "Participación general")
def _(c):
    r, ref, n_act = c.get("resultados"), _referencia(), _total_actividades(c)
    if not isinstance(r, pd.DataFrame) or ref is None or not n_act:
        return [(False, "Ejecuta primero las preguntas 4 y 5 (actividades y resultados).")] + [(False, "")]
    id_col = _col(ref, "IdAlumno")
    total = len(ref)
    opciones = {total / (n_act * ref[id_col].nunique())} if id_col else set()
    if isinstance(c.get("alumnos"), list) and c.get("alumnos"):
        opciones.add(total / (n_act * len(c.get("alumnos"))))
    nums = _nums(c)
    ok = any(_aparece(nums, v, 0.0051) or _aparece(nums, v * 100, 0.51) for v in opciones)
    return [
        (c.usa(r"\bactividades\b") or c.usa(r"\b" + str(n_act) + r"\b"),
         "Cantidad de actividades = suma de las actividades de cada tema (usa el diccionario actividades)."),
        (ok, "Muestra el porcentaje: participaciones / (cantidad de actividades × número de alumnos)."),
    ]


# ============================================================================ pregunta 07
@validacion("p07", "Participación por alumno")
def _(c):
    ref, n_act = _referencia(), _total_actividades(c)
    if ref is None or not n_act or _col(ref, "IdAlumno") is None:
        return [(False, "Ejecuta primero las preguntas 4 y 5 (actividades y resultados).")] + [(False, "")]
    esperado = {(str(k),): v / n_act for k, v in ref.groupby(_col(ref, "IdAlumno")).size().items()}
    ok = any(_coincide(o, esperado, escalas=(1, 100)) for o in _candidatos(c))
    return [
        (c.usa(r"\.groupby\s*\("), "Agrupa por alumno con .groupby('IdAlumno')."),
        (ok, "Calcula para cada alumno: participaciones / cantidad de actividades del curso."),
    ]


# ============================================================================ pregunta 08
@validacion("p08", "Actividades por alumno y tema")
def _(c):
    ref = _referencia()
    id_col, tema_col = _col(ref, "IdAlumno"), _col(ref, "Tema")
    if ref is None or id_col is None or tema_col is None:
        return [(False, "Ejecuta primero la pregunta 5 (resultados).")] + [(False, "")]
    esperado = {tuple(sorted(map(str, k))): float(v) for k, v in ref.groupby([id_col, tema_col]).size().items()}
    ok = any(_coincide(o, esperado) for o in _candidatos(c))
    return [
        (c.usa(r"\.groupby\s*\(\s*\["), "Agrupa por dos campos: .groupby(['IdAlumno', 'Tema'])."),
        (ok, "Muestra la cantidad de actividades registradas por cada alumno en cada tema."),
    ]


# ============================================================================ pregunta 09
@validacion("p09", "Seleccionar campos")
def _(c):
    r = c.get("resultados")
    if not isinstance(r, pd.DataFrame):
        return [(False, "Ejecuta primero la pregunta 5 (resultados).")] + [(False, "")]
    buscadas = {_clave(x) for x in ("IdAlumno", "Tema", "Actividad", "Participacion")}
    ok = any(isinstance(o, pd.DataFrame) and {_clave(x) for x in o.columns} == buscadas and len(o) == len(r)
             for o in _candidatos(c, (pd.DataFrame,)))
    return [
        (c.usa(r"resultados\s*\[\s*\["), "Selecciona varias columnas con doble corchete: resultados[['IdAlumno', ...]]."),
        (ok, "El resultado debe tener solo IdAlumno, Tema, Actividad y Participacion, con todos los registros."),
    ]


# ============================================================================ pregunta 10
@validacion("p10", "Filtrar tema Listas")
def _(c):
    r = c.get("resultados")
    tema = _col(r, "Tema")
    if not isinstance(r, pd.DataFrame) or tema is None:
        return [(False, "Ejecuta primero la pregunta 5 (resultados).")] + [(False, "")]
    n = int((r[tema].astype(str).map(_norm) == "listas").sum())
    ok = any(isinstance(o, pd.DataFrame) and _col(o, "Tema") is not None and len(o) == n
             and (o[_col(o, "Tema")].astype(str).map(_norm) == "listas").all()
             for o in _candidatos(c, (pd.DataFrame,)))
    return [
        (c.usa(r"resultados\s*\[\s*resultados\s*\[|\.query\s*\(|\.loc\s*\["), "Filtra con una condición: resultados[resultados['Tema'] == 'Listas']."),
        (ok, "El resultado debe contener solo los registros del tema Listas."),
    ]
