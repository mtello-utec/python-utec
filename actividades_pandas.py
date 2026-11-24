"""
actividades_pandas.py — Tema 5 · Pandas. Validación automática de actividades en Google Colab.

Celda de inicio del notebook:
    !curl -sL https://raw.githubusercontent.com/mtello-utec/python-utec/refs/heads/main/actividades_pandas.py -o actividades_pandas.py
    import importlib, actividades_pandas
    importlib.reload(actividades_pandas)
    actividades_pandas.iniciar()

Actividades: t5a01, t5a02, t5a03, t5a04, t5a05, t5a06, t5a07, t5a08, t5a09
Cada una se resuelve en una celda que empieza con:  %%actividad t5a01
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
CURSO = "UTEC Python M2 - Pandas"
VERSION = "2026-11-24 v6"
# ===============================================================================

ALUMNO = None
ESTADO = {}          # memoria entre actividades (p. ej. nombre de la lista inicial)
VALIDACIONES = {}    # id -> (titulo, funcion)

_IGNORAR = {"In", "Out", "exit", "quit", "get_ipython", "actividades_pandas"}


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
        print("⚠️ Primero ejecuta la celda de inicio (actividades_pandas.iniciar()).")
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
    ip.register_magic_function(actividad, "cell", "actividad")
    print(f"👋 Hola {ALUMNO}. Listo: resuelve cada actividad en su celda (empieza con %%actividad).  [versión {VERSION}]")


# ============================================================================ ACTIVIDADES
import os
import zipfile

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------- utilidades
def _clave(texto):
    """'Estado_Civil', 'estado civil', 'EstadoCivil' -> 'estadocivil'; 'Años'/'Anios' -> 'anos'."""
    return _norm(texto).replace(" ", "").replace("anios", "anos")


def _col(df, nombre):
    """Nombre real de la columna de df que corresponde a `nombre` (tolera mayúsculas, tildes, _ y espacios)."""
    if not isinstance(df, pd.DataFrame):
        return None
    buscada = _clave(nombre)
    for c in df.columns:
        if _clave(c) == buscada:
            return c
    return None


def _df(c, nombre):
    v = c.get(nombre)
    return v if isinstance(v, pd.DataFrame) else None


def _df_asignados(c):
    return [v for v in c.asignadas().values() if isinstance(v, pd.DataFrame)]


def _texto_crudo(c):
    return c.salida + ("" if c.valor is None else "\n" + str(c.valor))


def _nums(c):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", _texto_crudo(c).replace(",", ""))]


def _aparece(nums, valor, tol):
    return any(abs(n - valor) <= tol for n in nums)


def _expresiones_ocultas(codigo):
    """Expresiones sueltas que no son la última línea: Jupyter no las muestra."""
    try:
        cuerpo = ast.parse(codigo).body
    except SyntaxError:
        return 0
    ocultas = 0
    for nodo in cuerpo[:-1]:
        if isinstance(nodo, ast.Expr):
            f = nodo.value.func if isinstance(nodo.value, ast.Call) else None
            nombre = getattr(f, "id", None) or getattr(f, "attr", None)
            if nombre not in ("print", "display"):
                ocultas += 1
    return ocultas


def _proporcion(serie, valor):
    s = serie.astype(str).map(_norm)
    return (s == _norm(valor)).mean()


# ============================================================================ actividad 01
_D01_COLS = ["columna1", "Columna 2", "Col_03", "Columna 04"]


@validacion("t5a01", "Crear data01")
def _(c):
    d = _df(c, "data01")
    if d is None:
        return [(False, "Crea el DataFrame con el nombre exacto data01: data01 = pd.DataFrame({...}).")] + [(False, "")] * 3
    cols_ok = list(d.columns) == _D01_COLS
    if not cols_ok or len(d) != 3:
        return [
            (cols_ok, f"Las columnas deben llamarse exactamente {_D01_COLS} (respeta mayúsculas, espacios y _)."),
            (len(d) == 3, f"data01 tiene {len(d)} filas; deben ser 3."),
            (False, ""), (False, ""),
        ]
    c04 = list(d["Columna 04"])
    return [
        (True, ""),
        (list(d["columna1"]) == [1, 2, 3] and [str(x) for x in d["Columna 2"]] == ["A", "B", "C"],
         "Revisa columna1 (1, 2, 3) y Columna 2 ('A', 'B', 'C')."),
        (np.allclose(pd.to_numeric(d["Col_03"], errors="coerce").fillna(-1), [5.25, 4.13, 5.37]),
         "Col_03 debe tener los números 5.25, 4.13 y 5.37 (sin comillas)."),
        (not isinstance(c04[0], str) and c04[0] == True and not isinstance(c04[1], str) and c04[1] == False
         and not isinstance(c04[2], str) and pd.isna(c04[2]),
         "Columna 04: True y False sin comillas, y el tercer valor vacío (None o np.nan, no '')."),
    ]


# ============================================================================ actividad 02
@validacion("t5a02", "Simular data02")
def _(c):
    d = _df(c, "data02")
    if d is None:
        return [(False, "Crea el DataFrame con el nombre exacto data02.")] + [(False, "")] * 7
    cols = {k: _col(d, k) for k in ("Edad", "Sexo", "Estado Civil", "Ingreso", "Region", "Años trabajo")}
    faltan = [k for k, v in cols.items() if v is None]
    if faltan or len(d) != 400:
        return [
            (len(d) == 400, f"data02 tiene {len(d)} registros; deben ser 400 clientes."),
            (not faltan, f"Faltan columnas: {', '.join(faltan)}."),
        ] + [(False, "")] * 6
    edad, sexo, civil = d[cols["Edad"]], d[cols["Sexo"]], d[cols["Estado Civil"]]
    ingreso, region, anos = d[cols["Ingreso"]], d[cols["Region"]], d[cols["Años trabajo"]]

    def enteros_en(s, a, b):
        return pd.api.types.is_integer_dtype(s) and s.between(a, b).all()

    ing = pd.to_numeric(ingreso, errors="coerce")
    return [
        (True, ""),
        (c.usa(r"np\s*\.\s*random"), "Simula los datos con np.random (randint, choice, normal)."),
        (enteros_en(edad, 20, 60), "Edad: números enteros entre 20 y 60 (np.random.randint)."),
        (set(sexo.astype(str).map(_norm)) <= {"hombre", "mujer"}, "Sexo: solo 'Hombre' o 'Mujer'."),
        (set(civil.astype(str).map(_norm)) <= {"soltero", "casado"} and 0.70 <= _proporcion(civil, "Soltero") <= 0.90,
         "Estado Civil: 'Soltero' (80%) / 'Casado' (20%). Usa np.random.choice(..., p=[0.8, 0.2])."),
        (ing.notna().all() and 4600 <= ing.mean() <= 5400 and 1200 <= ing.std() <= 1800
         and np.allclose(ing, ing.round(2)),
         "Ingreso: normal con promedio 5000 y desviación 1500, redondeado a 2 decimales."),
        (set(region.astype(str).map(_norm)) <= {"lima", "provincia"} and 0.50 <= _proporcion(region, "Lima") <= 0.70,
         "Region: 'Lima' (60%) / 'Provincia' (40%)."),
        (enteros_en(anos, 1, 10), "Años trabajo: números enteros entre 1 y 10."),
    ]


# ============================================================================ actividad 03
@validacion("t5a03", "Acceso a datos de data02")
def _(c):
    d = _df(c, "data02")
    if d is None:
        return [(False, "Ejecuta primero la actividad t5a02 (data02).")] + [(False, "")] * 5
    cols = [_col(d, k) for k in ("Edad", "Sexo", "Estado Civil")]
    edad = re.escape(str(cols[0] or "Edad"))
    tres_ok = False
    for grupo in re.findall(r"data02\s*\[\s*\[([^\]]*)\]\s*\]", c.codigo_limpio):
        nombres = {_clave(x) for x in re.findall(r"['\"]([^'\"]+)['\"]", grupo)}
        tres_ok = tres_ok or {_clave("Edad"), _clave("Sexo"), _clave("Estado Civil")} <= nombres
    ocultas = _expresiones_ocultas(c.codigo)
    return [
        (c.usa(r"data02\s*\.\s*head\s*\(\s*7\s*\)|data02\s*(\.iloc\s*)?\[\s*0?\s*:\s*7\s*\]"),
         "Primeros 7 registros: data02.head(7)."),
        (c.usa(r"data02\s*\.\s*tail\s*\(\s*12\s*\)|data02\s*(\.iloc\s*)?\[\s*-12\s*:\s*\]"),
         "Últimos 12 registros: data02.tail(12)."),
        (c.usa(r"data02\s*(\.iloc\s*)?\[\s*1\s*:\s*3\s*\]|data02\s*\.\s*loc\s*\[\s*1\s*:\s*2\s*\]"),
         "Segunda y tercera fila: data02[1:3] (el índice empieza en 0)."),
        (c.usa(r"data02\s*\[\s*['\"]" + edad + r"['\"]\s*\]|data02\s*\.\s*" + edad + r"\b"),
         f"Columna Edad: data02['{cols[0] or 'Edad'}']."),
        (tres_ok, "Tres columnas con doble corchete: data02[['Edad', 'Sexo', 'Estado Civil']]."),
        (ocultas == 0, "Usa print() o display() para cada resultado: en una celda solo se muestra la última línea."),
    ]


# ============================================================================ actividad 04
@validacion("t5a04", "Exportar, leer y crear meses trabajo")
def _(c):
    d2 = _df(c, "data02")
    dt = _df(c, "dataset_train")
    checks = [
        (c.usa(r"data02\s*\.\s*to_csv\s*\("), "Exporta data02 con data02.to_csv('nombre.csv')."),
        (c.usa(r"pd\s*\.\s*read_csv\s*\(") and dt is not None,
         "Lee el archivo exportado y guárdalo como dataset_train = pd.read_csv(...)."),
    ]
    if dt is None:
        return checks + [(False, ""), (False, "")]
    anos, meses = _col(dt, "Años trabajo"), _col(dt, "meses trabajo")
    checks.append((d2 is None or len(dt) == len(d2), "dataset_train debe tener los mismos registros que data02."))
    checks.append((anos is not None and meses is not None
                   and np.allclose(pd.to_numeric(dt[meses]), pd.to_numeric(dt[anos]) * 12),
                   "Crea dataset_train['meses trabajo'] = años de trabajo × 12."))
    return checks


# ============================================================================ actividad 05
@validacion("t5a05", "Modificar df_pacientes")
def _(c):
    d = _df(c, "df_pacientes")
    if d is None:
        return [(False, "Crea el DataFrame con el nombre exacto df_pacientes.")] + [(False, "")] * 4
    falt = [k for k in ("Id", "Edad", "Sexo", "Altura", "Peso") if k not in d.columns]
    if falt or len(d) != 1_000_000:
        return [(not falt and len(d) == 1_000_000,
                 f"df_pacientes debe tener 1,000,000 registros y las columnas Id, Edad, Sexo, Altura, Peso"
                 + (f" (faltan: {', '.join(falt)})." if falt else "."))] + [(False, "")] * 4
    alt = pd.to_numeric(d["Altura"], errors="coerce")
    peso = pd.to_numeric(d["Peso"], errors="coerce")
    cm = _col(d, "AlturaCM")
    return [
        (True, ""),
        (set(d["Sexo"].astype(str).unique()) == {"Hombre", "Mujer"}, "Reetiqueta Sexo: 'M' → 'Hombre', 'F' → 'Mujer' (con map o replace)."),
        (np.allclose(alt, alt.round(2)), "Redondea Altura a dos decimales: df_pacientes['Altura'].round(2)."),
        (np.allclose(peso, peso.round(0)), "Redondea Peso a enteros: df_pacientes['Peso'].round()."),
        (cm is not None and np.allclose(pd.to_numeric(d[cm]), alt * 100, atol=0.51),
         "Crea df_pacientes['AlturaCM'] = df_pacientes['Altura'] * 100."),
    ]


# ============================================================================ actividad 06
def _hojas_excel(ruta):
    try:
        with zipfile.ZipFile(ruta) as z:
            xml = z.read("xl/workbook.xml").decode("utf-8", "ignore")
        return re.findall(r'<(?:\w+:)?sheet [^>]*name="([^"]+)"', xml)
    except Exception:
        return []


@validacion("t5a06", "Exportar en 4 formatos")
def _(c):
    csv_ok = os.path.exists("df_pacientes.csv")
    if csv_ok:
        with open("df_pacientes.csv", encoding="utf-8", errors="ignore") as f:
            csv_ok = "|" in f.readline()
    return [
        (c.usa(r"to_csv\s*\([^)]*sep\s*=\s*['\"]\|['\"]") and csv_ok,
         "CSV: df_pacientes.to_csv('df_pacientes.csv', sep='|')."),
        (c.usa(r"to_excel\s*\(") and "Pacientes" in _hojas_excel("df_pacientes.xlsx"),
         "Excel: df_pacientes.to_excel('df_pacientes.xlsx', sheet_name='Pacientes')."),
        (c.usa(r"to_pickle\s*\(") and os.path.exists("df_pacientes.pkl"),
         "Pickle: df_pacientes.to_pickle('df_pacientes.pkl')."),
        (c.usa(r"to_parquet\s*\(") and os.path.exists("df_pacientes.parquet"),
         "Parquet: df_pacientes.to_parquet('df_pacientes.parquet')."),
    ]


# ============================================================================ actividad 07
@validacion("t5a07", "Importar CSV con opciones")
def _(c):
    leidos = [v for v in _df_asignados(c) if set(v.columns) == {"Id", "Edad", "Sexo"}]
    d = leidos[0] if leidos else None
    return [
        (c.usa(r"read_csv\s*\([^)]*['\"]df_pacientes\.csv['\"]") and c.usa(r"sep\s*=\s*['\"]\|['\"]"),
         "Lee 'df_pacientes.csv' indicando sep='|'."),
        (c.usa(r"usecols\s*=") and d is not None, "Importa solo Id, Edad y Sexo con usecols=['Id', 'Edad', 'Sexo']."),
        (c.usa(r"dtype\s*=") and d is not None and pd.api.types.is_string_dtype(d["Id"])
         and d["Id"].astype(str).str.len().eq(4).all(),
         "Id debe leerse como texto (dtype={'Id': str, ...}) para conservar los ceros a la izquierda."),
        (d is not None and pd.api.types.is_integer_dtype(d["Edad"]) and pd.api.types.is_string_dtype(d["Sexo"]),
         "Tipos: Edad entero (int) y Sexo texto (str)."),
    ]


# ============================================================================ actividad 08
_STATS = [("Edad", "promedio", "mean"), ("Edad", "mínima", "min"), ("Edad", "máxima", "max"),
          ("Altura", "promedio", "mean"), ("Altura", "mínima", "min"), ("Altura", "máxima", "max"),
          ("Peso", "promedio", "mean"), ("Peso", "mínimo", "min"), ("Peso", "máximo", "max")]


@validacion("t5a08", "Estadísticas desde pickle")
def _(c):
    if not c.usa(r"read_pickle\s*\(\s*['\"]df_pacientes\.pkl['\"]"):
        return [(False, "Importa con pd.read_pickle('df_pacientes.pkl').")] + [(False, "")] * 3
    try:
        ref = pd.read_pickle("df_pacientes.pkl")
    except Exception:
        return [(False, "No se pudo leer df_pacientes.pkl: ejecuta primero la actividad t5a06.")] + [(False, "")] * 3
    nums = _nums(c)
    checks = [(True, "")]
    for var in ("Edad", "Altura", "Peso"):
        faltan = []
        for v, nombre, f in _STATS:
            if v != var:
                continue
            esperado = float(getattr(pd.to_numeric(ref[var]), f)())
            if not _aparece(nums, esperado, max(0.0051, abs(esperado) * 0.01)):
                faltan.append(nombre)
        checks.append((not faltan, f"{var}: falta mostrar {', '.join(faltan)}." if faltan else ""))
    return checks


# ============================================================================ actividad 09
@validacion("t5a09", "Filtrar pacientes")
def _(c):
    if not c.usa(r"read_pickle\s*\(\s*['\"]df_pacientes\.pkl['\"]"):
        return [(False, "Importa con pd.read_pickle('df_pacientes.pkl').")] + [(False, "")] * 2
    try:
        ref = pd.read_pickle("df_pacientes.pkl")
    except Exception:
        return [(False, "No se pudo leer df_pacientes.pkl: ejecuta primero la actividad t5a06.")] + [(False, "")] * 2
    n_h = int((ref["Sexo"] == "Hombre").sum())
    n_hj = int(((ref["Sexo"] == "Hombre") & (pd.to_numeric(ref["Edad"]) < 35)).sum())
    candidatos = [v for v in list(c.asignadas().values()) + [c.valor]
                  if isinstance(v, pd.DataFrame) and "Sexo" in v.columns and "Edad" in v.columns]
    solo_h = any(len(v) == n_h and (v["Sexo"] == "Hombre").all() for v in candidatos)
    final = any(len(v) == n_hj and (v["Sexo"] == "Hombre").all() and (pd.to_numeric(v["Edad"]) < 35).all()
                for v in candidatos)
    return [
        (True, ""),
        (solo_h or final, "Filtra los hombres: df[df['Sexo'] == 'Hombre']."),
        (final, f"Filtra además los menores de 35 años (Edad < 35): deben quedar {n_hj:,} pacientes."),
    ]
