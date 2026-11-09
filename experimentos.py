"""Experimentos de la Entrega 2 (versión final).

  E1  Comparación principal: manual vs greedy vs flujo (parámetros de parametros.json)
  E2  Toda la oferta académica CIT
  E3  Robustez frente al emparejamiento sección <-> grupo real
  E4  Pesos a, b, c sobre el triángulo a + b + c = 1 (selección de pesos)
  E5  No elegibles: umbrales x modo (excluir / dos pasadas / penalizar con d) y elección de d
  E6  Verificación del criterio lexicográfico y tiempos
  E7  Capacidades: máximo por alumno, bloque de corrección y no rankeados

Uso: python experimentos.py [--semillas 100] [--semillas-pesos 10]
Salida: salidas/resultados.xlsx
"""
import argparse
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from ayudantias import costos, datos, metricas, modelo, robustez
from ayudantias.config import Parametros

BASE = Path(__file__).parent
METRICAS_CORTAS = ["% cobertura", "alumnos distintos", "alumnos con 3+", "no elegibles asignados",
                   "% 1a prio profe", "% dentro de 3 del profe", "% 1a prio alumno", "% 1o por notas",
                   "P_O promedio", "P_E promedio", "P_A promedio"]
ACTORES = ["P_O promedio", "P_E promedio", "P_A promedio"]


def cargar(p):
    post = datos.cargar_postulaciones(BASE / "postulaciones_ayudantias_anonimo.xlsx")
    return costos.anotar(post, p), datos.cargar_oferta(BASE / "Horarios Ing_inf.xls")


def escenario(post, oferta, p, semilla=None):
    sec = datos.tabla_secciones(post, p.cupos, oferta, p.semilla if semilla is None else semilla)
    return sec, datos.horarios_de_oferta(sec)


def correr(post, oferta, p, semilla=None, claves=METRICAS_CORTAS):
    """Resuelve con p; si cambian los umbrales de elegibilidad, re-anota."""
    sec, hor = escenario(post, oferta, p, semilla)
    asign, info = modelo.resolver(post, sec, p, hor)
    m = metricas.calcular(asign, sec, p, hor)
    return {k: m[k] for k in claves}, info


def comparar(post, oferta, p):
    sec, hor = escenario(post, oferta, p)
    asign, info = modelo.resolver(post, sec, p, hor)
    t0 = time.perf_counter()
    greedy = modelo.greedy_por_seccion(post, sec, p, hor)
    t_greedy = time.perf_counter() - t0
    tabla = pd.DataFrame({
        "Histórico (manual)": metricas.calcular(modelo.historico(post), sec, p, hor),
        "Greedy por sección": metricas.calcular(greedy, sec, p, hor),
        "Flujo costo mínimo": metricas.calcular(asign, sec, p, hor),
    })
    tabla.loc["tiempo (ms)"] = [None, round(t_greedy * 1000), round(info["segundos"] * 1000)]
    return tabla, sec, asign, info


# --- E4: pesos ---------------------------------------------------------------
def triangulo(paso=0.1):
    n = round(1 / paso)
    return [(i / n, j / n, round(1 - i / n - j / n, 10)) for i in range(n + 1) for j in range(n + 1 - i)]


def barrido_pesos(post, oferta, p, semillas=range(10), paso=0.1):
    """Para cada proporción (a, b, c) del triángulo: insatisfacción media de cada actor.

    Con d > 0, los pesos efectivos son (1 - d)·(a, b, c); el triángulo es de proporciones.

    Selección (programación de compromiso): cada actor se normaliza entre su
    mejor valor (ideal) y su peor valor (nadir) en el triángulo, y se elige el
    punto más cercano al ideal (distancia euclidiana). Se reporta el óptimo
    libre y el óptimo con la jerarquía del Secretario (a >= b, a >= c).
    """
    filas = []
    for s in semillas:
        sec, hor = escenario(post, oferta, p, s)
        for a, b, c in triangulo(paso):
            q = p.con_pesos(a, b, c)  # proporciones a:b:c del triángulo, con el d de p
            asign, _ = modelo.resolver(post, sec, q, hor)
            m = metricas.calcular(asign, sec, q, hor)
            filas.append({"a": a, "b": b, "c": c, "semilla": s, **{k: m[k] for k in METRICAS_CORTAS}})
    df = pd.DataFrame(filas).drop(columns="semilla").groupby(["a", "b", "c"]).mean().reset_index()
    for k in ACTORES:
        lo, hi = df[k].min(), df[k].max()
        df[k.replace(" promedio", " norm")] = (df[k] - lo) / (hi - lo)
    norm = [k.replace(" promedio", " norm") for k in ACTORES]
    df["distancia al ideal"] = np.sqrt((df[norm] ** 2).sum(axis=1))
    df["jerarquía secretario"] = (df["a"] >= df["b"]) & (df["a"] >= df["c"])
    return df.round(4)


def elegir_pesos(df):
    libre = df.loc[df["distancia al ideal"].idxmin()]
    jer = df[df["jerarquía secretario"]]
    con_jer = jer.loc[jer["distancia al ideal"].idxmin()]
    return libre, con_jer


# --- E5: no elegibles --------------------------------------------------------
UMBRALES = [(4.5, 4.5), (5.0, 5.0), (5.0, 5.5), (5.2, 5.0), (5.4, 5.0)]
DELTAS = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8]


def modos(p):
    """(etiqueta, parámetros) para cada modo; a, b, c se reescalan a 1 - d (misma proporción)."""
    yield "excluir", p.con_pesos(d=0.0, modo_no_elegibles="excluir")
    yield "dos pasadas", p.con_pesos(d=0.0, modo_no_elegibles="dos_pasadas")
    for d in DELTAS:
        yield f"penalizar d={d}", p.con_pesos(d=d, modo_no_elegibles="penalizar")
    yield "sin criterio", p.con_pesos(d=0.0, modo_no_elegibles="penalizar")


def barrido_d(raw, oferta, p, semillas=range(5)):
    """No elegibles asignados por sobre el mínimo necesario (el de dos pasadas),
    peor caso sobre varios emparejamientos, para cada umbral y cada d."""
    filas = []
    for prom, nota in UMBRALES:
        q0 = p.con(promedio_minimo=prom, nota_minima_ramo=nota)
        post = costos.anotar(raw, q0)
        for s in semillas:
            minimo, _ = correr(post, oferta, q0.con_pesos(d=0.0, modo_no_elegibles="dos_pasadas"), s)
            for d in DELTAS:
                m, _ = correr(post, oferta, q0.con_pesos(d=d, modo_no_elegibles="penalizar"), s)
                filas.append({"umbral": f"{prom}/{nota}", "d": d, "semilla": s,
                              "exceso": m["no elegibles asignados"] - minimo["no elegibles asignados"],
                              "pierde cobertura": m["% cobertura"] < minimo["% cobertura"]})
    df = pd.DataFrame(filas)
    assert not df["pierde cobertura"].any()
    return df.groupby(["d", "umbral"])["exceso"].max().unstack()


def no_elegibles(raw, oferta, p):
    filas = []
    for prom, nota in UMBRALES:
        q0 = p.con(promedio_minimo=prom, nota_minima_ramo=nota)
        post = costos.anotar(raw, q0)
        for etiqueta, q in modos(q0):
            m, _ = correr(post, oferta, q, claves=METRICAS_CORTAS + ["cubiertos"])
            filas.append({"promedio mín.": prom, "nota mín.": nota, "modo": etiqueta,
                          "postulaciones no elegibles": int((~post["elegible"]).sum()), **m})
    return pd.DataFrame(filas).set_index(["promedio mín.", "nota mín.", "modo"])


# --- E6: lexicográfico -------------------------------------------------------
def verificar_lexicografico(post, oferta, p):
    """El flujo del SSP (todas las aristas, modo penalizar) debe igualar al
    flujo máximo sin costos (networkx) sobre la misma red."""
    filas = []
    q = p.con(modo_no_elegibles="penalizar")
    for cupos in ("historico", "todas", "oferta"):
        sec, hor = escenario(post, oferta, q.con(cupos=cupos))
        red, _ = modelo.construir_red(post, sec, q.con(cupos=cupos), hor)
        g = nx.DiGraph()
        for i in range(0, len(red.dst), 2):
            u, v = red.nombres[red.dst[i + 1]], red.nombres[red.dst[i]]
            c = red.cap[i]
            g.add_edge(u, v, capacity=g[u][v]["capacity"] + c if g.has_edge(u, v) else c)
        f_max = nx.maximum_flow_value(g, "S", "T")
        t0 = time.perf_counter()
        flujo, costo = red.resolver("S", "T")
        ms = round((time.perf_counter() - t0) * 1000)
        _, info = modelo.resolver(post, sec, p.con(cupos=cupos), hor)
        filas.append({"cupos": cupos, "cupos totales": int(sec["cupos"].sum()),
                      "nodos": len(red.nombres), "aristas": len(red.dst) // 2,
                      "flujo máximo (sin costos)": f_max, "flujo SSP": flujo, "tiempo SSP (ms)": ms,
                      "flujo dos pasadas": info["flujo"]})
    return pd.DataFrame(filas).set_index("cupos")


# --- E7: capacidades ---------------------------------------------------------
def capacidades(post, oferta, p):
    filas = []
    variantes = [(f"máx. {k} por alumno", p.con(max_ayudantias=k)) for k in (1, 2, 3, 4)]
    variantes += [(f"corrección cap. {k}", p.con(capacidad_correccion=k)) for k in (1, 2)]
    variantes += [("sin no rankeados", p.con(incluir_no_rankeados=False))]
    for nombre, q in variantes:
        for cupos in ("historico", "oferta"):
            m, _ = correr(post, oferta, q.con(cupos=cupos), claves=METRICAS_CORTAS + ["cubiertos", "cupos"])
            filas.append({"variante": nombre, "escenario": cupos, **m})
    return pd.DataFrame(filas).set_index(["variante", "escenario"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parametros", default=BASE / "parametros.json")
    ap.add_argument("--semillas", type=int, default=100, help="emparejamientos (E3)")
    ap.add_argument("--semillas-pesos", type=int, default=10, help="emparejamientos promediados en E4")
    args = ap.parse_args()
    pd.set_option("display.width", 220)

    p = Parametros.desde_json(args.parametros)
    raw = datos.cargar_postulaciones(BASE / "postulaciones_ayudantias_anonimo.xlsx")
    post = costos.anotar(raw, p)
    oferta = datos.cargar_oferta(BASE / "Horarios Ing_inf.xls")

    r = {}
    r["E1 comparación"], _, _, _ = comparar(post, oferta, p)
    r["E2 toda la oferta"], sec_o, asign_o, _ = comparar(post, oferta, p.con(cupos="oferta"))
    sin = modelo.no_cubiertas(asign_o, sec_o)
    r["E2 sin cubrir"] = (sin.assign(sin_postulantes=sin["postulantes"] == 0)
                          .groupby(["tipo", "sin_postulantes"]).size().unstack(fill_value=0))
    _, rob = robustez.analizar(post, p, oferta, range(args.semillas))
    r["E3 robustez"] = rob.T
    pesos = barrido_pesos(post, oferta, p, range(args.semillas_pesos))
    libre, jer = elegir_pesos(pesos)
    r["E4 pesos (triángulo)"] = pesos.set_index(["a", "b", "c"])
    r["E4 pesos elegidos"] = pd.DataFrame({"compromiso libre": libre, "con jerarquía (a>=b, a>=c)": jer})
    r["E5 no elegibles"] = no_elegibles(raw, oferta, p)
    r["E5 exceso por d"] = barrido_d(raw, oferta, p)
    r["E6 lexicográfico"] = verificar_lexicografico(post, oferta, p)
    r["E7 capacidades"] = capacidades(post, oferta, p)

    salida = BASE / "salidas" / "resultados.xlsx"
    salida.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(salida) as xls:
        for nombre, tabla in r.items():
            print(f"\n=== {nombre} ===")
            print(tabla.to_string())
            tabla.to_excel(xls, sheet_name=nombre[:31])
    print(f"\nResultados en {salida}")


if __name__ == "__main__":
    main()
