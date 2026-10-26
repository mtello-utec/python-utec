"""
actividades_listas.py — Tema 1 · Listas. Validación automática de actividades en Google Colab.

Celda de inicio del notebook:
    !curl -sL https://raw.githubusercontent.com/mtello-utec/python-utec/refs/heads/main/actividades_listas.py -o actividades_listas.py
    import actividades_listas
    actividades_listas.iniciar()

Actividades: t1a01, t1a02, t1a03, t1a04, t1a05, t1a06, t1a07, t1a08, t1a09, t1a10, t1a11, t1a12, t1a13, t1a14, t1a15, t1a16, t1a17, t1a18, t1a19, t1a20, t1a21
Cada una se resuelve en una celda que empieza con:  %%actividad t1a01
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
CURSO = "UTEC Python M2 - Listas"
VERSION = "2026-10-26 v2"
# ===============================================================================

ALUMNO = None
ESTADO = {}          # memoria entre actividades (p. ej. nombre de la lista inicial)
VALIDACIONES = {}    # id -> (titulo, funcion)

_IGNORAR = {"In", "Out", "exit", "quit", "get_ipython", "actividades_listas"}


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
        print("⚠️ Primero ejecuta la celda de inicio (actividades_listas.iniciar()).")
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
def _frase(c, partes):
    """partes alterna texto fijo y valores; revisa que la frase completa aparezca."""
    valores = [p for i, p in enumerate(partes) if i % 2 == 1]
    faltan = [str(v) for v in valores if _norm(v) not in c.texto()]
    if faltan:
        return False, f"En la frase faltan estos datos de tu lista: {', '.join(faltan)}."
    if not c.dijo(" ".join(str(p) for p in partes)):
        return False, "La frase no coincide con el texto pedido. Revisa que esté completa y en el orden indicado."
    return True, ""


def _info(c, cuando="ns"):
    l = (c.antes if cuando == "antes" else c.ns).get("info_personal")
    return l if isinstance(l, list) else None


def _nombres(c):
    k = ESTADO.get("nombres")
    if k and isinstance(c.antes.get(k), list):
        return k
    for k in ("nombres", "lista", "lista_nombres"):
        if isinstance(c.antes.get(k), list):
            return k
    return None


@validacion("t1a01", "Lista de 7 nombres")
def _(c):
    nuevas = c.listas_nuevas()
    if not nuevas:
        return [(False, "Crea una lista usando corchetes [ ]."), (False, "Debe tener 7 nombres."),
                (False, "Los elementos deben ser texto."), (False, "Imprime la lista.")]
    k = next((n for n in nuevas if len(c.ns[n]) == 7), nuevas[0])
    l = c.ns[k]
    ESTADO["nombres"] = k
    return [
        (True, ""),
        (len(l) == 7, f"La lista '{k}' tiene {len(l)} elementos; deben ser 7."),
        (all(isinstance(x, str) and x.strip() for x in l), "Todos los elementos deben ser nombres (texto entre comillas)."),
        (c.usa(r"print\s*\(") and c.mostro(l), f"Imprime la lista con print({k})."),
    ]


@validacion("t1a02", "Lista info_personal")
def _(c):
    l = _info(c)
    if l is None:
        return [(False, "Crea la lista con el nombre exacto info_personal.")] + [(False, "")] * 3
    if len(l) >= 6:
        ESTADO["centro_original"] = l[4]
    return [
        (len(l) == 6, f"info_personal tiene {len(l)} elementos; deben ser 6 (nombre, apellidoPaterno, profesión, edad, centroLaboral, añosExperiencia)."),
        (len(l) == 6 and all(isinstance(l[i], str) for i in (0, 1, 2, 4)), "nombre, apellido, profesión y centro laboral deben ser texto."),
        (len(l) == 6 and _es_num(l[3]) and _es_num(l[5]), "edad y añosExperiencia deben ser números (sin comillas)."),
        (re.search(r"heterog|mixt", _norm(c.codigo + " " + c.salida)) is not None,
         "Responde la pregunta: ¿qué tipo de lista es? (escríbelo en un comentario o con print)."),
    ]


@validacion("t1a03", "Acceder al 2.º elemento")
def _(c):
    l = _info(c)
    if l is None or len(l) < 2:
        return [(False, "Ejecuta primero la actividad t1a02 (info_personal)."), (False, "")]
    return [
        (c.usa(r"info_personal\s*\[\s*(1|-\d+)\s*\]"), "Accede con el índice correcto: el segundo elemento es el índice 1."),
        (c.mostro(l[1]), f"Muestra el valor del segundo elemento ({l[1]!r})."),
    ]


@validacion("t1a04", "Frase con info_personal")
def _(c):
    l = _info(c)
    if l is None or len(l) < 6:
        return [(False, "Ejecuta primero la actividad t1a02 (info_personal)."), (False, "")]
    return [
        (c.usa(r"info_personal\s*\["), "Usa los elementos de info_personal (por ejemplo info_personal[0]), no escribas los datos a mano."),
        _frase(c, ["Hola, me llamo", l[0], "", l[1], "soy", l[2], ", tengo", l[3],
                   "años, trabajo en la empresa", l[4], "y tengo", l[5], "años de experiencia profesional"]),
    ]


@validacion("t1a05", "Lista marcas y último elemento")
def _(c):
    l = c.get("marcas")
    if not isinstance(l, list) or not l:
        return [(False, "Crea la lista con el nombre exacto marcas."), (False, ""), (False, "")]
    return [
        (len(l) >= 3, "Agrega al menos 3 marcas."),
        (c.usa(r"marcas\s*\[\s*(-1|len\s*\(\s*marcas\s*\)\s*-\s*1)\s*\]"), "Accede al último elemento con marcas[-1]."),
        (c.mostro(l[-1]), f"Muestra el último elemento ({l[-1]!r})."),
    ]


@validacion("t1a06", "Modificar centro laboral")
def _(c):
    antes, l = _info(c, "antes"), _info(c)
    if antes is None or l is None or len(l) < 6:
        return [(False, "Ejecuta primero la actividad t1a02 (info_personal)."), (False, ""), (False, "")]
    original = ESTADO.get("centro_original", antes[4])
    return [
        (c.usa(r"info_personal\s*\[\s*(4|-2)\s*\]\s*="), "Modifica por índice: info_personal[4] = 'nueva empresa'."),
        (l[4] != original, "El centro laboral sigue igual; reemplázalo por la empresa donde te gustaría trabajar."),
        (len(l) == len(antes) and all(l[i] == antes[i] for i in range(len(l)) if i != 4),
         "Solo debe cambiar el centro laboral; el resto de la lista debe quedar igual."),
    ]


@validacion("t1a07", "Añadir un nombre")
def _(c):
    k = _nombres(c)
    if not k:
        return [(False, "Ejecuta primero la actividad t1a01 (lista de nombres)."), (False, ""), (False, "")]
    cambio = _agrego_uno(c.antes[k], c.ns.get(k, []))
    return [
        (cambio is not None, f"La lista '{k}' debe tener exactamente un nombre más que antes."),
        (cambio is not None and isinstance(cambio[1], str), "El nuevo elemento debe ser un nombre (texto)."),
        (c.usa(rf"{k}\s*\.\s*(append|insert)\s*\("), f"Usa {k}.append(...) para añadir el nombre."),
    ]


@validacion("t1a08", "Insertar centroEstudios")
def _(c):
    antes, l = _info(c, "antes"), _info(c)
    if antes is None or l is None:
        return [(False, "Ejecuta primero la actividad t1a02 (info_personal).")] + [(False, "")] * 3
    cambio = _agrego_uno(antes, l)
    ok_pos = cambio is not None and cambio[0] == 3 and isinstance(cambio[1], str)
    checks = [
        (cambio is not None, "info_personal debe tener exactamente un elemento más."),
        (ok_pos, "centroEstudios debe quedar en la cuarta posición (índice 3)."),
        (c.usa(r"info_personal\s*\.\s*insert\s*\(\s*3\s*,"), "Usa info_personal.insert(3, ...)."),
    ]
    if len(l) >= 7:
        checks.append(_frase(c, ["Hola, me llamo", l[0], "", l[1], "soy", l[2], ", estudié en la institución", l[3],
                                 ", tengo", l[4], "años, trabajo en la empresa", l[5], "y tengo", l[6],
                                 "años de experiencia profesional"]))
    else:
        checks.append((False, "Imprime la frase con centroEstudios."))
    return checks


@validacion("t1a09", "Eliminar con del")
def _(c):
    antes, l = c.antes.get("marcas"), c.get("marcas")
    if not isinstance(antes, list):
        return [(False, "Ejecuta primero la actividad t1a05 (lista marcas)."), (False, ""), (False, "")]
    quitado = _quito_uno(antes, l or [])
    tenia_coca = any(_norm(x) == "coca cola" for x in antes)
    return [
        (quitado is not None, "marcas debe tener exactamente un elemento menos."),
        (not tenia_coca or (quitado is not None and _norm(quitado) == "coca cola"),
         "Debes eliminar 'coca cola'."),
        (c.usa(r"\bdel\s+marcas\s*\["), "Usa la instrucción del marcas[índice]."),
    ]


@validacion("t1a10", "Eliminar y guardar con pop")
def _(c):
    k = _nombres(c)
    if not k:
        return [(False, "Ejecuta primero la actividad t1a01 (lista de nombres).")] + [(False, "")] * 3
    antes, l = c.antes[k], c.ns.get(k, [])
    guardados = [v for n, v in {**c.cambiadas(), **c.asignadas()}.items() if n != k and isinstance(v, str)]
    return [
        (len(antes) >= 3 and l == antes[:1] + antes[2:-1], "Deben eliminarse el elemento de índice 1 y el último."),
        (len(antes) >= 2 and antes[1] in guardados and antes[-1] in guardados,
         "Guarda cada elemento eliminado en una variable (x = lista.pop(...))."),
        (c.usa(rf"=\s*{k}\s*\.\s*pop\s*\(\s*1\s*\)"), f"Usa {k}.pop(1) para el de índice 1."),
        (c.usa(rf"=\s*{k}\s*\.\s*pop\s*\(\s*(-1)?\s*\)"), f"Usa {k}.pop() para el último."),
    ]


@validacion("t1a11", "Eliminar por valor con remove")
def _(c):
    antes, l = c.antes.get("marcas"), c.get("marcas")
    if not isinstance(antes, list):
        return [(False, "Ejecuta primero la actividad t1a05 (lista marcas)."), (False, "")]
    return [
        (_quito_uno(antes, l or []) is not None, "marcas debe tener exactamente un elemento menos."),
        (c.usa(r"marcas\s*\.\s*remove\s*\(\s*['\"]"), "Elimina por valor: marcas.remove('marca'), sin usar índices."),
    ]


@validacion("t1a12", "Ordenar permanente")
def _(c):
    l = c.get("paises")
    if not isinstance(l, list):
        return [(False, "Crea la lista con el nombre exacto paises.")] + [(False, "")] * 3
    return [
        (len(l) == 5 and all(isinstance(x, str) for x in l), "paises debe tener 5 países (texto)."),
        (c.usa(r"paises\s*\.\s*sort\s*\(\s*\)"), "Ordena ascendente con paises.sort()."),
        (c.usa(r"paises\s*\.\s*sort\s*\(\s*reverse\s*=\s*True\s*\)"), "Ordena descendente con paises.sort(reverse=True)."),
        (l == sorted(l, reverse=True), "Al final, paises debe quedar ordenada de forma descendente."),
    ]


@validacion("t1a13", "Ordenar temporal")
def _(c):
    l = c.get("paises")
    if not isinstance(l, list):
        return [(False, "Crea la lista con el nombre exacto paises.")] + [(False, "")] * 4
    return [
        (len(l) == 5 and all(isinstance(x, str) for x in l), "paises debe tener 5 países (texto)."),
        (c.usa(r"sorted\s*\(\s*paises\s*\)"), "Ordena ascendente con sorted(paises)."),
        (c.usa(r"sorted\s*\(\s*paises\s*,\s*reverse\s*=\s*True\s*\)"), "Ordena descendente con sorted(paises, reverse=True)."),
        (not c.usa(r"\.\s*sort\s*\("), "No uses .sort(): eso ordena de forma permanente."),
        (c.mostro(sorted(l)) and c.mostro(sorted(l, reverse=True)), "Imprime ambos resultados con print()."),
    ]


_UNIS = ["pucp", "usil", "esan", "ulima", "usmp", "utec"]


@validacion("t1a14", "Universidades en reversa")
def _(c):
    l = c.get("universidades")
    if not isinstance(l, list):
        return [(False, "Crea la lista con el nombre exacto universidades."), (False, "")]
    norm = [_norm(x) for x in l]
    return [
        (norm in (_UNIS, _UNIS[::-1]), "La lista debe tener: 'pucp', 'usil', 'esan', 'ulima', 'usmp', 'utec'."),
        (c.en_orden(_UNIS[::-1]), "Imprime los elementos en orden inverso (de 'utec' a 'pucp')."),
    ]


@validacion("t1a15", "Cantidad de elementos")
def _(c):
    l = _info(c)
    if l is None:
        return [(False, "Ejecuta primero la actividad t1a02 (info_personal)."), (False, "")]
    return [
        (c.usa(r"len\s*\(\s*info_personal\s*\)"), "Usa len(info_personal)."),
        (c.mostro(len(l)), f"Muestra el resultado ({len(l)})."),
    ]


@validacion("t1a16", "Lista de compras con for")
def _(c):
    l = c.get("productos")
    if not isinstance(l, list):
        return [(False, "Crea la lista con el nombre exacto productos.")] + [(False, "")] * 3
    return [
        (len(l) >= 3, "Agrega al menos 3 productos."),
        (c.usa(r"\bfor\s+\w+\s+in\s+productos\b"), "Recorre la lista con: for producto in productos:"),
        (c.dijo("Mi lista de compra habitual en el supermercado es"), "Imprime la frase inicial completa."),
        (c.en_orden(l), "Imprime todos los productos, en el orden de la lista."),
    ]


_LIBS = ["Numpy", "Pandas", "Scipy", "Matplotlib", "Scikit Learn"]


@validacion("t1a17", "Librerías de Python")
def _(c):
    return [
        (c.usa(r"\bfor\b"), "Guarda las librerías en una lista y recórrela con for."),
        (c.dijo("Las librerías más usadas en Python son"), "Imprime la frase inicial completa."),
        (c.en_orden(_LIBS), "Imprime las 5 librerías: Numpy, Pandas, Scipy, Matplotlib, Scikit Learn."),
        (c.dijo("Tengo experiencia profesional trabajando con todas ellas"), "Imprime la frase final."),
    ]


@validacion("t1a18", "Países que quiero visitar")
def _(c):
    l = c.get("paises")
    if not isinstance(l, list):
        return [(False, "Crea la lista con el nombre exacto paises.")] + [(False, "")] * 3
    return [
        (c.usa(r"\bfor\s+\w+\s+in\s+paises\b"), "Recorre la lista con: for pais in paises:"),
        (c.dijo("Los países que me gustaría conocer son"), "Imprime la frase inicial completa."),
        (len(l) >= 2 and c.en_orden(l), "Imprime todos los países de tu lista."),
        (c.dijo("Estos países se caracterizan por"), "Cierra con: Estos países se caracterizan por ..."),
    ]


_CORR = list(range(10, 21))


@validacion("t1a19", "Correlativos 10 a 20 con for")
def _(c):
    l = c.get("correlativos")
    numeros = re.findall(r"-?\d+", c.salida)
    return [
        (isinstance(l, list), "Crea la lista con el nombre exacto correlativos."),
        (l == _CORR, "correlativos debe tener los números del 10 al 20 (usa list(range(10, 21)))."),
        (c.usa(r"\bfor\s+\w+\s+in\s+correlativos\b"), "Recorre la lista con: for n in correlativos:"),
        (all(str(n) in numeros for n in _CORR), "Imprime todos los valores del 10 al 20."),
    ]


@validacion("t1a20", "Comprensión de listas")
def _(c):
    l = c.get("correlativosn")
    return [
        (c.get("correlativos") == _CORR, "Crea la lista correlativos con los números del 10 al 20."),
        (isinstance(l, list) and l == list(range(15, 26)), "correlativosn debe contener cada valor + 5 (del 15 al 25)."),
        (c.usa(r"correlativosn\s*=\s*\[[^\]]*\bfor\b[^\]]*\bin\b[^\]]*\]"),
         "Usa comprensión de listas: correlativosn = [x + 5 for x in correlativos]."),
        (isinstance(l, list) and c.mostro(l), "Muestra correlativosn en pantalla."),
    ]


@validacion("t1a21", "Últimas 3 universidades")
def _(c):
    l = c.get("universidades", "universidad")
    if not isinstance(l, list) or len(l) < 3:
        return [(False, "Ejecuta primero la actividad t1a14 (lista universidades)."), (False, "")]
    return [
        (c.usa(r"universidad(es)?\s*\[\s*(-3|len\s*\(\s*universidad(es)?\s*\)\s*-\s*3)\s*:\s*\]"),
         "Usa slicing: universidades[-3:]."),
        (c.mostro(l[-3:]), f"Muestra el resultado ({l[-3:]})."),
    ]
