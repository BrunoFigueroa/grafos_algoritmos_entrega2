"""Genera figuras (figuras/*.pdf), tablas y cifras (tablas/*.tex) del informe de la Entrega 2.

Todo se calcula desde el modelo; ninguna cifra del informe se transcribe a mano.
Uso (desde Entrega_2/):  .venv/bin/python informe/generar_figuras.py
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import experimentos  # noqa: E402
from ayudantias import costos, datos, metricas, modelo, robustez  # noqa: E402
from ayudantias.config import Parametros  # noqa: E402

FIG = Path(__file__).parent / "figuras"
TAB = Path(__file__).parent / "tablas"
PNG = FIG / "png"
FIG.mkdir(exist_ok=True)
PNG.mkdir(exist_ok=True)
TAB.mkdir(exist_ok=True)

# --- estilo (paleta de referencia validada, modo claro / impresión) ---------
SUPERFICIE = "#fcfcfb"
TEXTO = "#0b0b0b"
TEXTO_2 = "#52514e"
GRILLA = "#e4e3de"
NEUTRO = "#b9b8b1"
COLOR = {  # un color fijo por método en todo el informe
    "Flujo costo mínimo": "#2a78d6",
    "Greedy por sección": "#eb6834",
    "Histórico (manual)": "#1baf7a",
}
METODOS = ["Histórico (manual)", "Greedy por sección", "Flujo costo mínimo"]
CORTO = {"Histórico (manual)": "Manual", "Greedy por sección": "Greedy",
         "Flujo costo mínimo": "Flujo"}
AZULES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "savefig.facecolor": SUPERFICIE,
    "font.size": 8.5, "axes.titlesize": 9, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.edgecolor": GRILLA, "axes.labelcolor": TEXTO_2, "xtick.color": TEXTO_2, "ytick.color": TEXTO_2,
    "text.color": TEXTO, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRILLA,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False,
    "lines.linewidth": 1.6, "hatch.color": SUPERFICIE, "hatch.linewidth": 1.2,
})
ANCHO = 6.3  # pulgadas = ancho de texto con márgenes de 2,5 cm


def guardar(fig, nombre):
    fig.savefig(FIG / f"{nombre}.pdf", bbox_inches="tight")
    fig.savefig(PNG / f"{nombre}.png", bbox_inches="tight", dpi=150)  # para el README
    plt.close(fig)
    print("  figura", nombre)


def num(x, dec=1):
    """Número con coma decimal (es-CL)."""
    if isinstance(x, (int, np.integer)) or dec == 0:
        return f"{round(float(x)):,}".replace(",", ".")
    return f"{x:.{dec}f}".replace(".", ",")


def rotular(ax, barras, dec=0, sufijo=""):
    for b in barras:
        h = b.get_height()
        ax.annotate(num(h, dec) + sufijo, (b.get_x() + b.get_width() / 2, h), xytext=(0, 2),
                    textcoords="offset points", ha="center", va="bottom", fontsize=7.5, color=TEXTO)


def tabla_tex(df, nombre, columnas=None, alinear=None, formatos=None):
    """DataFrame -> tabular booktabs (solo el entorno tabular; caption en el .tex)."""
    formatos = formatos or {}
    columnas = columnas or list(df.columns)
    alinear = alinear or "l" + "r" * (len(columnas) - 1)
    lineas = [rf"\begin{{tabular}}{{{alinear}}}", r"\toprule",
              " & ".join(rf"\textbf{{{c}}}" for c in columnas) + r" \\", r"\midrule"]
    for _, fila in df.iterrows():
        celdas = []
        for c in columnas:
            v = fila[c]
            f = formatos.get(c)
            celdas.append(f(v) if f else (num(v, 1) if isinstance(v, float) else str(v)))
        lineas.append(" & ".join(celdas) + r" \\")
    lineas += [r"\bottomrule", r"\end{tabular}"]
    (TAB / f"{nombre}.tex").write_text("\n".join(lineas) + "\n")
    print("  tabla", nombre)


def esc(s):
    return str(s).replace("&", r"\&").replace("%", r"\%").replace("_", r"\_").replace("#", r"\#")


ACTOR = {  # un color fijo por actor (slots 4-6 de la paleta categórica, validados)
    "P_O promedio": ("#eda100", "Profesor ($P^O$)"),
    "P_E promedio": ("#e87ba4", "Estudiante ($P^E$)"),
    "P_A promedio": ("#008300", "Asignatura ($P^A$)"),
}
# modos ordenados de más flexible a más estricto (rampa ordinal azul validada)
MODOS = [("penalizar d=0.1", "Penalizar d=0,1", "#86b6ef"), ("penalizar d=0.3", "Penalizar d=0,3", "#3987e5"),
         ("penalizar d=0.6", "Penalizar d=0,6 (base)", "#1c5cab"), ("excluir", "Excluir", "#0d366b")]


def macros(nombre, valores):
    """Escribe \\newcommand{\\clave}{valor} para usar cifras en el texto del informe."""
    (TAB / f"{nombre}.tex").write_text("".join(rf"\newcommand{{\{k}}}{{{v}}}" + "\n" for k, v in valores.items()))
    print("  macros", nombre)



# ---------------------------------------------------------------------------
def main():
    print("Cargando datos y resolviendo escenarios...")
    p = Parametros.desde_json(RAIZ / "parametros.json")
    raw = datos.cargar_postulaciones(RAIZ / "postulaciones_ayudantias_anonimo.xlsx")
    post = costos.anotar(raw, p)
    oferta = datos.cargar_oferta(RAIZ / "Horarios Ing_inf.xls")
    sec = datos.tabla_secciones(post, p.cupos, oferta, p.semilla)
    hor = datos.horarios_de_oferta(sec)
    asign, info = modelo.resolver(post, sec, p, hor)
    sol = {
        "Histórico (manual)": modelo.historico(post),
        "Greedy por sección": modelo.greedy_por_seccion(post, sec, p, hor),
        "Flujo costo mínimo": asign,
    }
    met = {m: metricas.calcular(a, sec, p, hor) for m, a in sol.items()}

    datos_resumen(post, oferta, sec, p)
    situacion_actual(post, oferta, met["Histórico (manual)"])
    tabla_comparacion(met, info, p)
    fig_metricas_clave(met)
    fig_actores(met)
    fig_carga(sol)
    fig_prioridades(sol)
    fig_solucion_grafo(post, sec, hor, sol)
    fig_horario(sol["Flujo costo mínimo"], sec, oferta)
    fig_oferta(post, oferta, p)
    fig_robustez(post, oferta, p)
    fig_pesos(post, oferta, p)
    fig_no_elegibles(raw, oferta, p)
    tabla_lexicografico(post, oferta, p)
    tabla_capacidades(post, oferta, p)
    anexo_asignacion(asign, sec)
    print("Listo.")


# --- datos ------------------------------------------------------------------
def datos_resumen(post, oferta, sec, p):
    g = post.groupby("seccion")
    filas = [
        ("Postulaciones", num(len(post), 0)),
        ("Postulantes (alumnos)", num(post["alumno"].nunique(), 0)),
        ("Cursos con postulaciones", num(post["sigla"].nunique(), 0)),
        ("Postulaciones por alumno (media / máx.)",
         f"{num(post.groupby('alumno').size().mean(), 1)} / {post.groupby('alumno').size().max()}"),
        ("Postulaciones sin ranking del profesor", num(int(post["prio_profe"].isna().sum()), 0)),
        ("Secciones reconstruidas", num(int((sec["postulantes"] > 0).sum()), 0)),
        ("Secciones sin ningún ranking del profesor", str(int((g["prio_profe"].count() == 0).sum()))),
        ("Elegidos en el proceso real", num(int(post["elegido_historico"].sum()), 0)),
        ("Cursos CIT en la oferta", num(oferta["sigla"].nunique(), 0)),
        ("Unidades ofertadas (cátedra / corrector / lab.)",
         " / ".join(str(oferta["tipo"].value_counts()[t]) for t in ["Cátedra", "Corrector", "Laboratorio"])),
    ]
    tabla_tex(pd.DataFrame(filas, columns=["Dato", "Valor"]), "datos")
    tipos = post.groupby("tipo").agg(post_=("alumno", "size"), eleg=("elegido_historico", "sum"))
    tipos = tipos.reset_index().rename(columns={"tipo": "Tipo", "post_": "Postulaciones", "eleg": "Elegidos"})
    tabla_tex(tipos, "datos_tipo", formatos={"Elegidos": lambda v: str(int(v))})
    ne = post[~post["elegible"]]
    macros("eleg_info", {
        "elegPromMin": num(p.promedio_minimo), "elegNotaMin": num(p.nota_minima_ramo),
        "elegPostNo": str(len(ne)), "elegPostTotal": num(len(post), 0),
        "elegAlumNoProm": str(int((~post.groupby("alumno")["cumple_promedio"].first()).sum())),
        "elegHistNo": str(int((~post["elegible"] & post["elegido_historico"]).sum())),
        "sinRankSecciones": str(int((g["prio_profe"].count() == 0).sum())),
        "sinRankPost": str(int(post["prio_profe"].isna().sum())),
    })


# --- situación actual (diagnóstico del proceso manual) -----------------------
def situacion_actual(post, oferta, met_hist):
    n_post = post.groupby("alumno").size()
    top = n_post.sort_values(ascending=False).head(round(len(n_post) * 0.1))
    elegidos = post[post["elegido_historico"]]
    defecto = post[post["seccion"].isin(set(elegidos["seccion"])) & (post["prio_profe"] == 1)]
    carga_def = defecto.groupby("alumno").size()
    primeros = post[post["prio_profe"] == 1].groupby("alumno").size()
    rech_1 = post[(post["prio_profe"] == 1) & ~post["elegido_historico"]]
    sin_ayud = set(n_post.index) - set(elegidos["alumno"])
    top3 = set(post.loc[post["prio_profe"] <= 3, "alumno"])
    sec_of = datos.tabla_secciones(post, "oferta", oferta, 0)
    of = sec_of[sec_of["cupos"] > 0]
    filas = [
        ("Alumnos que postulan a más de 3 ayudantías (el tope)",
         f"{(n_post > 3).sum()} de {len(n_post)} ({num(100 * (n_post > 3).mean())} \\%)"),
        ("Postulaciones del 10 \\% de alumnos que más postula", f"{num(100 * top.sum() / len(post))} \\%"),
        ("Alumnos que son 1ª prioridad del profesor en más de 3 secciones",
         f"{(primeros > 3).sum()} (máx. {primeros.max()})"),
        ("Asignación por defecto (1ª del profesor): alumnos sobre el tope",
         f"{(carga_def > 3).sum()} (máx. {carga_def.max()} ayudantías)"),
        ("Postulaciones rechazadas siendo 1ª prioridad del profesor",
         f"{len(rech_1)} ({(rech_1['prio_alumno'] == 1).sum()} también 1ª del alumno)"),
        ("Alumnos con ayudantía (proceso manual)", f"{met_hist['alumnos distintos']} de {len(n_post)}"),
        ("Alumnos sin ayudantía que estaban en el top 3 de algún profesor", str(len(sin_ayud & top3))),
        ("Alumnos con 3 ayudantías (proceso manual)", str(met_hist["alumnos con 3+"])),
        ("Asignaciones fuera de la 1ª prioridad del profesor",
         f"{num(100 - met_hist['% 1a prio profe'])} \\% ({int((elegidos['prio_profe'] > 1).sum())})"),
        ("Asignados que no cumplen el criterio de elegibilidad", str(met_hist["no elegibles asignados"])),
        ("Topes horarios entre ayudantías (proceso manual)", str(met_hist["choques horarios"])),
        ("Unidades de la oferta CIT sin ningún postulante",
         f"{int((of['postulantes'] == 0).sum())} de {len(of)}"),
    ]
    tabla_tex(pd.DataFrame(filas, columns=["Indicador", "Valor"]), "situacion", alinear="lr")

    fig, axs = plt.subplots(1, 2, figsize=(ANCHO, 2.5), gridspec_kw={"width_ratios": [1.25, 1]})
    bins = [(1, 1, "1"), (2, 2, "2"), (3, 3, "3"), (4, 5, "4–5"), (6, 10, "6–10"), (11, 20, "11–20"),
            (21, 999, ">20")]
    v = [int(n_post.between(a, b).sum()) for a, b, _ in bins]
    b = axs[0].bar([e for *_, e in bins], v, width=0.7,
                   color=[NEUTRO if a <= 3 else COLOR["Greedy por sección"] for a, *_ in bins])
    rotular(axs[0], b)
    axs[0].set_title("Postulaciones por alumno")
    axs[0].set_ylabel("Alumnos")
    axs[0].set_ylim(0, max(v) * 1.25)
    axs[0].axvline(2.5, color=TEXTO_2, linewidth=0.8, linestyle="--")
    axs[0].text(2.4, max(v) * 1.12, "tope de 3", fontsize=7, color=TEXTO_2, ha="right")
    cats = ["1", "2", "3", "4", "5+"]
    v = [int((carga_def == k).sum()) for k in (1, 2, 3, 4)] + [int((carga_def >= 5).sum())]
    b = axs[1].bar(cats, v, width=0.7, color=[NEUTRO] * 3 + [COLOR["Greedy por sección"]] * 2)
    rotular(axs[1], b)
    axs[1].set_title("Asignación por defecto (1ª del profesor)")
    axs[1].set_xlabel("Ayudantías por alumno")
    axs[1].set_ylim(0, max(v) * 1.25)
    fig.tight_layout(w_pad=2)
    guardar(fig, "situacion_actual")


# --- E1 ---------------------------------------------------------------------
def tabla_comparacion(met, info, p):
    filas = [
        ("Cupos cubiertos", "cubiertos", 0, ""), ("Cobertura", "% cobertura", 1, r" \%"),
        ("Alumnos con ayudantía", "alumnos distintos", 0, ""), ("Alumnos con 1", "alumnos con 1", 0, ""),
        ("Alumnos con 2", "alumnos con 2", 0, ""), ("Alumnos con 3", "alumnos con 3+", 0, ""),
        ("Excesos del tope de 3", "excesos de tope", 0, ""),
        ("Topes horarios entre ayudantías", "choques horarios", 0, ""),
        ("No elegibles asignados", "no elegibles asignados", 0, ""),
        ("1ª prioridad del profesor", "% 1a prio profe", 1, r" \%"),
        ("Dentro de los 3 primeros del profesor", "% dentro de 3 del profe", 1, r" \%"),
        ("1ª prioridad del alumno", "% 1a prio alumno", 1, r" \%"),
        ("Prioridad promedio del alumno", "prio alumno promedio", 2, ""),
        ("1° de la sección por notas", "% 1o por notas", 1, r" \%"),
        (r"$\bar P^O$ (profesor)", "P_O promedio", 3, ""),
        (r"$\bar P^E$ (estudiante)", "P_E promedio", 3, ""),
        (r"$\bar P^A$ (asignatura)", "P_A promedio", 3, ""),
        ("Costo total (misma función)", "costo (misma función)", 2, ""),
    ]
    df = pd.DataFrame([{"Métrica": n, **{CORTO[m]: num(met[m][k], d) + s for m in METODOS}}
                       for n, k, d, s in filas])
    tabla_tex(df, "comparacion", alinear="lrrr")
    f, h, g = (met[m] for m in ("Flujo costo mínimo", "Histórico (manual)", "Greedy por sección"))
    macros("red_info", {
        "redNodos": info["nodos"], "redAristas": info["aristas"], "redMs": round(info["segundos"] * 1000),
        "redPasadaUno": info["flujo_pasada_1"], "redPasadaDos": info.get("flujo_pasada_2", 0),
        "pesoA": num(p.a, 2), "pesoB": num(p.b, 2), "pesoC": num(p.c, 2), "pesoD": num(p.d),
        "propA": num(p.proporciones()[0]), "propB": num(p.proporciones()[1]), "propC": num(p.proporciones()[2]),
        "fAlumnos": f["alumnos distintos"], "hAlumnos": h["alumnos distintos"], "gAlumnos": g["alumnos distintos"],
        "fTres": f["alumnos con 3+"], "hTres": h["alumnos con 3+"], "gTres": g["alumnos con 3+"],
        "fCob": num(f["% cobertura"]), "gCob": num(g["% cobertura"]), "gCubiertos": g["cubiertos"],
        "fNoEleg": f["no elegibles asignados"], "hNoEleg": h["no elegibles asignados"],
        "gNoEleg": g["no elegibles asignados"], "hChoques": h["choques horarios"],
        "fPrimProf": num(f["% 1a prio profe"]), "hPrimProf": num(h["% 1a prio profe"]),
        "gPrimProf": num(g["% 1a prio profe"]), "fTresProf": num(f["% dentro de 3 del profe"]),
        "fPromAlum": num(f["prio alumno promedio"], 2), "hPromAlum": num(h["prio alumno promedio"], 2),
        "fNotas": num(f["% 1o por notas"]), "hNotas": num(h["% 1o por notas"]),
        "fCosto": num(f["costo (misma función)"], 2), "hCosto": num(h["costo (misma función)"], 2),
        "gCosto": num(g["costo (misma función)"], 2),
    })


def fig_metricas_clave(met):
    paneles = [("Cobertura (%)", "% cobertura", 1), ("Topes horarios", "choques horarios", 0),
               ("No elegibles", "no elegibles asignados", 0),
               ("Costo total", "costo (misma función)", 1)]
    fig, axs = plt.subplots(1, 4, figsize=(ANCHO, 2.1))
    for ax, (titulo, k, dec) in zip(axs, paneles):
        vals = [met[m][k] for m in METODOS]
        b = ax.bar([CORTO[m] for m in METODOS], vals, width=0.6, color=[COLOR[m] for m in METODOS])
        rotular(ax, b, dec)
        ax.set_title(titulo, fontsize=8.5)
        ax.set_ylim(0, max(vals) * 1.22 if max(vals) else 1)
        ax.tick_params(axis="x", labelsize=7.5)
        if k == "% cobertura":
            ax.set_ylim(90, 101.5)
    fig.tight_layout(w_pad=1.2)
    guardar(fig, "metricas_clave")


def fig_actores(met):
    """Insatisfacción media de cada actor (0 = todos obtienen su 1ª opción)."""
    fig, ax = plt.subplots(figsize=(ANCHO * 0.62, 2.3))
    x = np.arange(len(METODOS))
    ancho = 0.8 / 3
    for i, (k, (color, nombre)) in enumerate(ACTOR.items()):
        vals = [met[m][k] for m in METODOS]
        b = ax.bar(x + (i - 1) * ancho, vals, width=ancho * 0.9, color=color, label=nombre)
        rotular(ax, b, 2)
    ax.set_xticks(x, [CORTO[m] for m in METODOS])
    ax.set_ylabel("Penalización media (0 = 1ª opción)")
    ax.set_ylim(0, 0.45)
    ax.legend(ncols=3, loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=7)
    fig.tight_layout()
    guardar(fig, "actores")


def _barras_agrupadas(ax, categorias, series, dec=0):
    n = len(series)
    ancho = 0.8 / n
    x = np.arange(len(categorias))
    for i, (nombre, vals) in enumerate(series.items()):
        b = ax.bar(x + (i - (n - 1) / 2) * ancho, vals, width=ancho * 0.92, color=COLOR[nombre],
                   label=CORTO[nombre])
        rotular(ax, b, dec)
    ax.set_xticks(x, categorias)


def fig_carga(sol):
    fig, ax = plt.subplots(figsize=(ANCHO * 0.56, 2.3))
    cats = ["1", "2", "3"]
    series = {m: [int((sol[m].groupby("alumno").size() == k).sum()) for k in (1, 2, 3)] for m in METODOS}
    _barras_agrupadas(ax, cats, series)
    ax.set_xlabel("Ayudantías asignadas al alumno")
    ax.set_ylabel("Alumnos")
    ax.set_ylim(0, max(max(v) for v in series.values()) * 1.4)
    ax.legend(ncols=3, loc="upper right", fontsize=7.5)
    fig.tight_layout()
    guardar(fig, "carga_alumnos")


def fig_prioridades(sol):
    fig, axs = plt.subplots(2, 1, figsize=(ANCHO, 4.4))
    cats_p = ["1", "2", "3", "4+"]
    series = {m: [int((sol[m]["rank_profe_ef"] == r).sum()) for r in (1, 2, 3)] +
              [int((sol[m]["rank_profe_ef"] >= 4).sum())] for m in METODOS}
    _barras_agrupadas(axs[0], cats_p, series)
    axs[0].set_title("Posición en el ranking del profesor")
    axs[0].set_ylabel("Asignaciones")
    axs[0].set_ylim(0, 135)
    bins = [(1, 1, "1"), (2, 2, "2"), (3, 3, "3"), (4, 5, "4–5"), (6, 10, "6–10"), (11, 999, ">10")]
    series = {m: [int(sol[m]["prio_alumno"].between(a, b).sum()) for a, b, _ in bins] for m in METODOS}
    _barras_agrupadas(axs[1], [e for *_, e in bins], series)
    axs[1].set_title("Posición en la lista del alumno")
    axs[1].set_ylim(0, 60)
    axs[1].set_ylabel("Asignaciones")
    axs[0].legend(ncols=3, loc="upper right", fontsize=7.5)
    fig.tight_layout(h_pad=1.5)
    guardar(fig, "prioridades")


# --- solución como grafo ----------------------------------------------------
def _elegir_caso(post, sol, sec_unidad):
    """Curso (tipo cátedra) chico donde el flujo y el manual difieren."""
    mejor = None
    for (sigla, tipo), g in post[post["tipo"] == "Cátedra"].groupby(["sigla", "tipo"]):
        if g["seccion"].nunique() < 2 or len(g) > 14 or g["seccion"].map(sec_unidad).isna().any():
            continue
        a = set(sol["Flujo costo mínimo"].query("sigla == @sigla and tipo == @tipo")["id_postulacion"])
        h = set(sol["Histórico (manual)"].query("sigla == @sigla and tipo == @tipo")["id_postulacion"])
        dif = len(a ^ h)
        if mejor is None or dif > mejor[0]:
            mejor = (dif, sigla, tipo)
    return mejor[1], mejor[2]


def fig_solucion_grafo(post, sec, hor, sol):
    sigla, tipo = _elegir_caso(post, sol, sec["unidad"])
    g = post[(post["sigla"] == sigla) & (post["tipo"] == tipo)]
    secciones = sorted(g["seccion"].unique())
    alumnos_ = sorted(g["alumno"].unique())
    carga = {m: sol[m].groupby("alumno").size() for m in METODOS}
    fig, axs = plt.subplots(1, 2, figsize=(ANCHO, 3.3))
    ys_a = {a: i for i, a in enumerate(reversed(alumnos_))}
    ys_s = {s: (len(alumnos_) - 1) * (i + 0.5) / len(secciones) for i, s in enumerate(secciones)}
    for ax, m in zip(axs, ["Histórico (manual)", "Flujo costo mínimo"]):
        elegidas = set(sol[m]["id_postulacion"])
        ax.set_axis_off()
        for f in g.itertuples():
            y0, y1 = ys_a[f.alumno], ys_s[f.seccion]
            si = f.id_postulacion in elegidas
            ax.plot([0, 1], [y0, y1], color=COLOR[m] if si else GRILLA, lw=2.2 if si else 0.8,
                    zorder=3 if si else 1, solid_capstyle="round")
            if si:
                ax.annotate(f"P{int(f.rank_profe_ef)}" + ("" if pd.notna(f.prio_profe) else "*"),
                            (0.18, y0 + (y1 - y0) * 0.18), fontsize=6.5, color=TEXTO_2,
                            ha="center", va="bottom")
        for a, y in ys_a.items():
            k = int(carga[m].get(a, 0))
            ax.scatter([0], [y], s=34, color=COLOR[m] if k else NEUTRO, edgecolor=SUPERFICIE,
                       linewidth=1.5, zorder=4)
            ax.text(-0.05, y, f"{a}  ({k})", ha="right", va="center", fontsize=7, color=TEXTO)
        for s, y in ys_s.items():
            ax.scatter([1], [y], s=70, marker="s", color=TEXTO_2, edgecolor=SUPERFICIE, zorder=4)
            etiqueta = sec.at[s, "unidad"] or s
            bloque = hor.get(s, "sin bloque")
            ax.text(1.05, y, f"{etiqueta}\n{bloque}", ha="left", va="center", fontsize=6.8, color=TEXTO)
        ax.set_xlim(-0.55, 1.6)
        ax.set_title(f"{CORTO[m]}: {sigla} {tipo.lower()}", loc="center")
    fig.text(0.5, -0.02, "Alumno (ayudantías totales que recibe en todo el proceso)  →  grupo de ayudantía "
             "(bloque).  Línea gruesa = asignado; Pk = posición k en el ranking del profesor.",
             ha="center", fontsize=7, color=TEXTO_2)
    fig.tight_layout()
    guardar(fig, "solucion_grafo")
    (TAB / "caso_grafo.tex").write_text(rf"\newcommand{{\casoSigla}}{{{sigla}}}" + "\n")


# --- horario -----------------------------------------------------------------
def fig_horario(asign, sec, oferta):
    dias = ["LU", "MA", "MI", "JU", "VI"]
    inicios = ["08:30", "10:00", "11:30", "13:00", "14:30", "16:00", "17:25"]
    ofer = np.zeros((len(inicios), len(dias)), int)
    asig = np.zeros_like(ofer)
    for b in oferta["bloque"].dropna():
        d, h = b.split()
        if h in inicios:
            ofer[inicios.index(h), dias.index(d)] += 1
    for s in asign["seccion"]:
        b = sec.at[s, "bloque"] if "bloque" in sec else None
        if isinstance(b, str):
            d, h = b.split()
            if h in inicios:
                asig[inicios.index(h), dias.index(d)] += 1
    fig, axs = plt.subplots(1, 2, figsize=(ANCHO, 2.7))
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(AZULES)
    cmap.set_bad(SUPERFICIE)
    vmax = ofer.max()
    for ax, mat, titulo in [(axs[0], ofer, "Ayudantías y laboratorios ofertados (CIT)"),
                            (axs[1], asig, "Ayudantes asignados por el flujo")]:
        ax.grid(False)
        ax.imshow(np.ma.masked_equal(mat, 0), cmap=cmap, vmin=1, vmax=vmax, aspect="auto")
        for i in range(len(inicios)):
            for j in range(len(dias)):
                v = mat[i, j]
                ax.text(j, i, str(v) if v else "", ha="center", va="center", fontsize=7.5,
                        color="white" if v > vmax * 0.55 else TEXTO)
        ax.set_xticks(range(len(dias)), dias)
        ax.set_yticks(range(len(inicios)), inicios)
        ax.set_title(titulo)
        ax.tick_params(length=0)
    fig.tight_layout(w_pad=2)
    guardar(fig, "horario")


def fig_robustez(post, oferta, p, n=100):
    detalle, resumen = robustez.analizar(post, p, oferta, range(n))
    fig, axs = plt.subplots(1, 3, figsize=(ANCHO, 2.3))
    for ax, k, titulo in [(axs[0], "alumnos distintos", "Alumnos con ayudantía"),
                          (axs[1], "costo (misma función)", "Costo total")]:
        datos_k = [detalle[detalle["método"] == m][k].to_numpy() for m in METODOS]
        rng = np.random.default_rng(0)
        for i, (m, v) in enumerate(zip(METODOS, datos_k)):
            ax.scatter(i + rng.uniform(-0.18, 0.18, len(v)), v, s=9, color=COLOR[m], alpha=0.55,
                       edgecolor="none")
            ax.plot([i - 0.28, i + 0.28], [v.mean()] * 2, color=TEXTO, lw=1.2)
        ax.set_xticks(range(3), [CORTO[m] for m in METODOS])
        ax.set_title(titulo)
    hist = detalle[detalle["método"] == "Histórico (manual)"]["choques horarios"].value_counts().sort_index()
    b = axs[2].bar(hist.index.astype(str), hist.values, color=COLOR["Histórico (manual)"], width=0.6)
    rotular(axs[2], b)
    axs[2].set_title("Topes del manual (frecuencia)")
    axs[2].set_xlabel(f"topes horarios en {n} emparejamientos")
    axs[2].set_ylim(0, hist.max() * 1.25)
    fig.tight_layout(w_pad=1.5)
    guardar(fig, "robustez")
    r = resumen.T
    filas = []
    for k, nombre, dec in [("% cobertura", r"Cobertura (\%)", 1), ("alumnos distintos", "Alumnos con ayudantía", 1),
                           ("alumnos con 3+", "Alumnos con 3", 1), ("choques horarios", "Topes horarios", 1),
                           ("no elegibles asignados", "No elegibles asignados", 1),
                           ("P_O promedio", r"$\bar P^O$ (profesor)", 3),
                           ("P_E promedio", r"$\bar P^E$ (estudiante)", 3),
                           ("P_A promedio", r"$\bar P^A$ (asignatura)", 3),
                           ("costo (misma función)", "Costo total", 2)]:
        fila = {"Métrica": nombre}
        for m in METODOS:
            lo, hi, me = r.loc[(k, "min"), m], r.loc[(k, "max"), m], r.loc[(k, "mean"), m]
            fila[CORTO[m]] = num(me, dec) if lo == hi else f"{num(me, dec)} [{num(lo, dec)}–{num(hi, dec)}]"
        filas.append(fila)
    tabla_tex(pd.DataFrame(filas), "robustez", alinear="lrrr")


# --- E2 ----------------------------------------------------------------------
def fig_oferta(post, oferta, p):
    q = p.con(cupos="oferta")
    sec = datos.tabla_secciones(post, q.cupos, oferta, q.semilla)
    hor = datos.horarios_de_oferta(sec)
    asign, _ = modelo.resolver(post, sec, q, hor)
    con = sec[sec["cupos"] > 0].copy()
    con["cubierto"] = con.index.isin(asign["seccion"])
    con["estado"] = np.where(con["cubierto"], "Cubierto",
                             np.where(con["postulantes"] == 0, "Sin postulantes", "Sin cubrir (con postulantes)"))
    tab = con.groupby(["tipo", "estado"]).size().unstack(fill_value=0)
    estados = ["Cubierto", "Sin cubrir (con postulantes)", "Sin postulantes"]
    colores = {"Cubierto": COLOR["Flujo costo mínimo"], "Sin cubrir (con postulantes)": "#eb6834",
               "Sin postulantes": NEUTRO}
    tipos = ["Laboratorio", "Corrector", "Cátedra"]
    fig, axs = plt.subplots(1, 2, figsize=(ANCHO, 3.6), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axs[0]
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    izq = np.zeros(len(tipos))
    for e in estados:
        v = np.array([tab.loc[t, e] if e in tab and t in tab.index else 0 for t in tipos])
        ax.barh(tipos, v, left=izq, color=colores[e], height=0.55, label=e, edgecolor=SUPERFICIE, linewidth=1.5)
        for y, (l, w) in enumerate(zip(izq, v)):
            if w >= 6:
                ax.text(l + w / 2, y, str(w), ha="center", va="center", fontsize=7.5,
                        color="white" if e == "Cubierto" else TEXTO)
        izq += v
    for y, total in enumerate(izq):
        ax.text(total + 1.5, y, f"{int(total)}", va="center", fontsize=7.5, color=TEXTO_2)
    ax.set_title("Unidades ofertadas por tipo y estado")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncols=2, fontsize=7)
    ax.set_xlim(0, izq.max() * 1.12)
    vacias = con[con["postulantes"] == 0].groupby("sigla").size().sort_values()
    ax = axs[1]
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.barh(vacias.index, vacias.values, color=NEUTRO, height=0.65)
    for y, v in enumerate(vacias.values):
        ax.text(v + 0.1, y, str(v), va="center", fontsize=6.8, color=TEXTO_2)
    ax.set_title("Unidades sin postulantes, por curso")
    ax.tick_params(axis="y", labelsize=6.5)
    fig.tight_layout(w_pad=2)
    guardar(fig, "oferta")
    m = metricas.calcular(asign, sec, q, hor)
    h = metricas.calcular(modelo.historico(post), sec, q, hor)
    gr = metricas.calcular(modelo.greedy_por_seccion(post, sec, q, hor), sec, q, hor)
    sin = con[~con["cubierto"]]
    macros("oferta_info", {
        "ofCupos": m["cupos"], "ofFlujo": m["cubiertos"], "ofFlujoPct": num(m["% cobertura"]),
        "ofGreedy": gr["cubiertos"], "ofHist": h["cubiertos"], "ofSinCubrir": len(sin),
        "ofSinPost": int((sin["postulantes"] == 0).sum()),
        "ofSinPostLab": int(((sin["postulantes"] == 0) & (sin["tipo"] == "Laboratorio")).sum()),
        "ofNoRank": m["no rankeados asignados"], "ofNoEleg": m["no elegibles asignados"],
    })


# --- E4: pesos ---------------------------------------------------------------
def _ternario(a, b, c):
    """a -> vértice inferior izquierdo, b -> inferior derecho, c -> superior."""
    return np.asarray(b) + np.asarray(c) / 2, np.asarray(c) * np.sqrt(3) / 2


def fig_pesos(post, oferta, p, n_semillas=10):
    df = experimentos.barrido_pesos(post, oferta, p, range(n_semillas))
    libre, jer = experimentos.elegir_pesos(df)
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("azul", AZULES)
    paneles = [("P_O promedio", "Profesor  $\\bar P^O$"), ("P_E promedio", "Estudiante  $\\bar P^E$"),
               ("P_A promedio", "Asignatura  $\\bar P^A$"), ("distancia al ideal", "Distancia al ideal")]
    fig, axs = plt.subplots(1, 4, figsize=(ANCHO, 1.95))
    x, y = _ternario(df["a"], df["b"], df["c"])
    for ax, (k, titulo) in zip(axs, paneles):
        ax.set_axis_off()
        ax.set_aspect("equal")
        ax.plot([0, 1, 0.5, 0], [0, 0, np.sqrt(3) / 2, 0], color=GRILLA, lw=0.8, zorder=0)
        ax.scatter(x, y, c=df[k], cmap=cmap, s=26, marker="h", edgecolor="none", zorder=2)
        for punto, marca in [(libre, "o"), (jer, "s")]:
            px, py = _ternario(punto["a"], punto["b"], punto["c"])
            ax.scatter([px], [py], s=58, marker=marca, facecolor="none", edgecolor=TEXTO, lw=1.2, zorder=3)
        ax.text(-0.04, -0.05, "a", ha="right", va="top", fontsize=7.5, color=TEXTO_2)
        ax.text(1.04, -0.05, "b", ha="left", va="top", fontsize=7.5, color=TEXTO_2)
        ax.text(0.5, np.sqrt(3) / 2 + 0.05, "c", ha="center", va="bottom", fontsize=7.5, color=TEXTO_2)
        ax.set_title(titulo, fontsize=7.8, loc="center", pad=10)
        lo, hi = df[k].min(), df[k].max()
        ax.text(0.5, -0.2, f"claro {num(lo, 2)}  →  oscuro {num(hi, 2)}", ha="center", fontsize=6.3,
                color=TEXTO_2)
    fig.tight_layout(w_pad=0.6)
    guardar(fig, "pesos")
    # tabla: vértices, centro y los dos elegidos
    def fila(nombre, r):
        return {"Configuración": nombre, "a": num(r["a"]), "b": num(r["b"]), "c": num(r["c"]),
                r"$\bar P^O$": num(r["P_O promedio"], 3), r"$\bar P^E$": num(r["P_E promedio"], 3),
                r"$\bar P^A$": num(r["P_A promedio"], 3), r"1ª prof. (\%)": num(r["% 1a prio profe"]),
                r"Top 3 prof. (\%)": num(r["% dentro de 3 del profe"]), "Alumnos": num(r["alumnos distintos"]),
                "Dist.": num(r["distancia al ideal"], 3)}

    def buscar(a, b, c):
        return df[(df["a"].round(2) == a) & (df["b"].round(2) == b) & (df["c"].round(2) == c)].iloc[0]
    filas = [fila("Solo profesor", buscar(1, 0, 0)), fila("Solo estudiante", buscar(0, 1, 0)),
             fila("Solo asignatura", buscar(0, 0, 1)),
             fila(r"Compromiso libre ($\circ$)", libre), fila(r"Con jerarquía ($\square$)", jer)]
    tabla_tex(pd.DataFrame(filas), "pesos", alinear="lrrrrrrrrrr")
    macros("pesos_info", {
        "libreA": num(libre["a"]), "libreB": num(libre["b"]), "libreC": num(libre["c"]),
        "jerA": num(jer["a"]), "jerB": num(jer["b"]), "jerC": num(jer["c"]),
        "pesosN": len(df), "pesosSemillas": n_semillas,
        "jerPrimProf": num(jer["% 1a prio profe"]), "librePrimProf": num(libre["% 1a prio profe"]),
        "jerTresProf": num(jer["% dentro de 3 del profe"]), "libreTresProf": num(libre["% dentro de 3 del profe"]),
    })


# --- E5: no elegibles --------------------------------------------------------
def fig_no_elegibles(raw, oferta, p):
    df = experimentos.no_elegibles(raw, oferta, p).reset_index()
    df["umbral"] = [f"{num(a)} / {num(b)}" for a, b in zip(df["promedio mín."], df["nota mín."])]
    umbrales = list(dict.fromkeys(df["umbral"]))
    fig, axs = plt.subplots(1, 2, figsize=(ANCHO, 2.5))
    x = np.arange(len(umbrales))
    ancho = 0.8 / len(MODOS)
    for ax, k, titulo, dec in [(axs[0], "% cobertura", "Cobertura (%)", 1),
                               (axs[1], "no elegibles asignados", "No elegibles asignados", 0)]:
        for i, (modo, etiqueta, color) in enumerate(MODOS):
            v = df[df["modo"] == modo].set_index("umbral").loc[umbrales, k]
            b = ax.bar(x + (i - (len(MODOS) - 1) / 2) * ancho, v, width=ancho * 0.9, color=color, label=etiqueta)
            if k != "% cobertura":
                for barra in b:
                    ax.annotate(str(int(barra.get_height())), (barra.get_x() + barra.get_width() / 2,
                                barra.get_height()), xytext=(0, 1.5), textcoords="offset points",
                                ha="center", va="bottom", fontsize=6, color=TEXTO)
        ax.set_xticks(x, umbrales)
        ax.tick_params(axis="x", labelsize=6.8)
        ax.set_xlabel("promedio mínimo / nota mínima del ramo")
        ax.set_title(titulo)
    axs[0].set_ylim(80, 102)
    axs[1].set_ylim(0, df["no elegibles asignados"].max() * 1.2)
    fig.legend(*axs[0].get_legend_handles_labels(), ncols=4, loc="lower center",
               bbox_to_anchor=(0.5, 0.98), fontsize=7)
    fig.tight_layout(w_pad=1.5)
    guardar(fig, "no_elegibles")
    # tabla compacta: todos los modos en el umbral base
    base = df[(df["promedio mín."] == p.promedio_minimo) & (df["nota mín."] == p.nota_minima_ramo)]
    nombres = {"excluir": "Excluir", "dos pasadas": "Dos pasadas", "sin criterio": "Sin criterio (d = 0)"}
    t = pd.DataFrame({
        "Modo": [nombres.get(m, m.replace("penalizar d=", "Penalizar d = ").replace(".", ",")) for m in base["modo"]],
        "Cubiertos": base["cubiertos"].astype(int).astype(str),
        "No eleg.": base["no elegibles asignados"].astype(int).astype(str),
        "Alumnos": base["alumnos distintos"].astype(int).astype(str),
        r"1ª prof. (\%)": base["% 1a prio profe"].map(num),
        r"$\bar P^O$": base["P_O promedio"].map(lambda v: num(v, 3)),
        r"$\bar P^E$": base["P_E promedio"].map(lambda v: num(v, 3)),
        r"$\bar P^A$": base["P_A promedio"].map(lambda v: num(v, 3)),
    })
    tabla_tex(t, "no_elegibles", alinear="lrrrrrrr")
    # tabla por umbral: excluir vs dos pasadas
    filas = []
    for u in umbrales:
        g = df[df["umbral"] == u].set_index("modo")
        filas.append({"Umbral": u, "Post. no eleg.": str(int(g["postulaciones no elegibles"].iloc[0])),
                      "Excluir: cub.": str(int(g.loc["excluir", "cubiertos"])),
                      "2 pasadas: cub.": str(int(g.loc["dos pasadas", "cubiertos"])),
                      "2 pasadas: no eleg.": str(int(g.loc["dos pasadas", "no elegibles asignados"])),
                      "$d=0{,}6$: cub.": str(int(g.loc["penalizar d=0.6", "cubiertos"])),
                      "$d=0{,}6$: no eleg.": str(int(g.loc["penalizar d=0.6", "no elegibles asignados"]))})
    tabla_tex(pd.DataFrame(filas), "umbrales", alinear="lrrrrrr")
    # elección de d: no elegibles por sobre el mínimo necesario (peor caso en 5 emparejamientos)
    ex = experimentos.barrido_d(raw, oferta, p)
    t = ex.reset_index()
    t.columns = ["d"] + [c.replace("/", " / ").replace(".", ",") for c in ex.columns]
    t["d"] = t["d"].map(lambda v: num(v, 2))
    for c in t.columns[1:]:
        t[c] = t[c].astype(int).astype(str)
    tabla_tex(t, "exceso_d", alinear="r" * len(t.columns))
    d_min = min(d for d, fila in ex.iterrows() if (fila == 0).all() and all(
        (ex.loc[e] == 0).all() for e in ex.index if e >= d))
    b = base.set_index("modo")
    macros("noeleg_info", {
        "neExcluirCub": int(b.loc["excluir", "cubiertos"]),
        "neDosCub": int(b.loc["dos pasadas", "cubiertos"]),
        "neDosNo": int(b.loc["dos pasadas", "no elegibles asignados"]),
        "nePenChicoNo": int(b.loc["penalizar d=0.05", "no elegibles asignados"]),
        "nePenGrandeNo": int(b.loc["penalizar d=0.6", "no elegibles asignados"]),
        "nePenMedioNo": int(b.loc["penalizar d=0.3", "no elegibles asignados"]),
        "neSinCritNo": int(b.loc["sin criterio", "no elegibles asignados"]),
        "neDCritico": num(d_min),
    })


# --- E6 ----------------------------------------------------------------------
def tabla_lexicografico(post, oferta, p):
    t = experimentos.verificar_lexicografico(post, oferta, p).reset_index()
    t = t.rename(columns={"cupos": "Escenario", "cupos totales": "Cupos", "nodos": "Nodos", "aristas": "Aristas",
                          "flujo máximo (sin costos)": "Flujo máx.", "flujo SSP": "Flujo SSP",
                          "tiempo SSP (ms)": "Tiempo (ms)", "flujo dos pasadas": "Dos pasadas"})
    t["Escenario"] = t["Escenario"].map({"historico": "histórico", "todas": "todas", "oferta": "oferta"})
    for c in t.columns[1:]:
        t[c] = t[c].map(lambda v: num(int(v), 0))
    tabla_tex(t, "lexicografico", alinear="lrrrrrrr")


# --- E7 ----------------------------------------------------------------------
def tabla_capacidades(post, oferta, p):
    df = experimentos.capacidades(post, oferta, p).reset_index()
    filas = []
    for v, g in df.groupby("variante", sort=False):
        h, o = g.set_index("escenario").loc["historico"], g.set_index("escenario").loc["oferta"]
        base = v == f"máx. {p.max_ayudantias} por alumno"
        filas.append({"Variante": v.replace("máx.", "Máx.").replace("corrección", "Corrección")
                      .replace("sin no", "Sin no") + (" (base)" if base else ""),
                      "Cubiertos (127)": str(int(h["cubiertos"])), "Alumnos (127)": str(int(h["alumnos distintos"])),
                      "Con 3": str(int(h["alumnos con 3+"])), r"1ª prof. (\%)": num(h["% 1a prio profe"]),
                      f"Cubiertos ({int(o['cupos'])})": str(int(o["cubiertos"])),
                      f"Alumnos ({int(o['cupos'])})": str(int(o["alumnos distintos"]))})
    tabla_tex(pd.DataFrame(filas), "capacidades", alinear="lrrrrrr")
    d = df.set_index(["variante", "escenario"])
    macros("cap_info", {
        "capDosAlumnos": int(d.loc[("máx. 2 por alumno", "historico"), "alumnos distintos"]),
        "capDosCub": int(d.loc[("máx. 2 por alumno", "historico"), "cubiertos"]),
        "capDosPrim": num(d.loc[("máx. 2 por alumno", "historico"), "% 1a prio profe"]),
        "capUnoCub": int(d.loc[("máx. 1 por alumno", "historico"), "cubiertos"]),
        "capCorrUnoAlumnos": int(d.loc[("corrección cap. 1", "historico"), "alumnos distintos"]),
        "capCorrUnoOf": int(d.loc[("corrección cap. 1", "oferta"), "cubiertos"]),
        "capSinRankOf": int(d.loc[("sin no rankeados", "oferta"), "cubiertos"]),
        "capBaseOf": int(d.loc[(f"máx. {p.max_ayudantias} por alumno", "oferta"), "cubiertos"]),
    })


# --- anexo -------------------------------------------------------------------
def anexo_asignacion(asign, sec):
    t = modelo.a_tabla(asign, sec)
    enc = (r"\textbf{Sigla} & \textbf{Tipo} & \textbf{Unidad} & \textbf{Alumno} & \textbf{R. prof.} & "
           r"\textbf{P. alum.} & \textbf{Eleg.} & \textbf{Bloque} \\")
    lineas = [r"\begin{longtable}{llllrrcl}",
              r"\caption{Asignación completa propuesta por el flujo (escenario base).}\label{tab:anexo}\\",
              r"\toprule", enc, r"\midrule", r"\endfirsthead",
              r"\toprule", enc, r"\midrule", r"\endhead",
              r"\bottomrule", r"\endfoot"]
    for f in t.itertuples():
        unidad = f.unidad if isinstance(f.unidad, str) else "—"
        bloque = f.bloque if isinstance(f.bloque, str) else "—"
        rp = f"{int(f.rank_profe_ef)}" + ("" if pd.notna(f.prio_profe) else "*")
        lineas.append(f"{f.sigla} & {f.tipo} & {esc(unidad)} & {f.alumno} & {rp} & {int(f.prio_alumno)} & "
                      f"{'sí' if f.elegible else 'no'} & {bloque} \\\\")
    lineas.append(r"\end{longtable}")
    (TAB / "anexo_asignacion.tex").write_text("\n".join(lineas) + "\n")
    print("  tabla anexo_asignacion")


if __name__ == "__main__":
    main()
