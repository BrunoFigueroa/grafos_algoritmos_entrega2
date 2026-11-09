"""Red S -> E -> H -> C -> T y lectura de la asignación.

Toda restricción dura es una capacidad; el único costo está en H -> C.

  S -> E_i        capacidad k_i = max_ayudantias - externas_i, costo 0.
  E_i -> H_i,h    capacidad 1, costo 0: a lo más una ayudantía por bloque h.
  E_i -> H_i,corr capacidad min(capacidad_correccion, k_i), costo 0: bloque
                  ficticio para las unidades sin horario (corrector o bloque
                  desconocido). Así todas las aristas de postulación salen de
                  la capa H y el corrector no compite por un bloque real.
  H -> C_j        capacidad 1, costo c_ij (ver costos.py). Solo si hubo
                  postulación y la arista está permitida (elegibilidad).
  C_j -> T        q_j aristas paralelas de capacidad 1 y costo 0 (una por cupo).

Modos para los no elegibles (Parametros.modo_no_elegibles):
  penalizar    (por defecto) una pasada con todos; los no elegibles cuestan
               + d. Con d alto (>= 0,6 en los datos) solo entran si no hay
               ningún elegible que cubra el cupo; con d menor, flexibilidad.
  dos_pasadas  1ª pasada solo elegibles; 2ª pasada sobre lo que sobra
               (cupos sin cubrir, capacidad y bloques libres) solo con no
               elegibles. La 2ª pasada nunca desplaza a un elegible.
  excluir      sin arista: quedan para decisión manual.
"""
import time

import pandas as pd

from .costos import arista_permitida, costo_arista
from .flujo import RedFlujo

CORR = "corrección"  # etiqueta del bloque ficticio


def tope(alumno, p):
    """k_i: máximo de ayudantías que puede recibir el alumno en esta asignación."""
    return max(0, p.max_ayudantias - int(p.externas.get(alumno, 0)))


def construir_red(post, secciones, p, horarios=None, pasada=1, previas=None):
    """Arma la red. `previas` (asignaciones ya fijadas) descuenta capacidad."""
    horarios = horarios or {}
    previas = previas if previas is not None else post.iloc[:0]
    carga = previas.groupby("alumno").size()
    bloques_usados = {(a, horarios.get(s, CORR)) for a, s in zip(previas["alumno"], previas["seccion"])}
    corr_usada = previas[~previas["seccion"].isin(horarios)].groupby("alumno").size()
    cubiertos = previas.groupby("seccion").size()

    red = RedFlujo()
    red.nodo("S")
    red.nodo("T")
    cap_e = {}
    for alumno in post["alumno"].unique():
        k = tope(alumno, p) - int(carga.get(alumno, 0))
        if k > 0:
            red.arista("S", ("E", alumno), k, 0)
            cap_e[alumno] = k

    aristas, capa_h = {}, set()
    for f in post.itertuples():
        libres = int(secciones.at[f.seccion, "cupos"]) - int(cubiertos.get(f.seccion, 0))
        if f.alumno not in cap_e or libres <= 0 or not arista_permitida(f, p, pasada):
            continue
        bloque = horarios.get(f.seccion, CORR)
        if bloque != CORR and (f.alumno, bloque) in bloques_usados:
            continue
        h = ("H", f.alumno, bloque)
        if h not in capa_h:
            if bloque == CORR:
                cap = min(p.capacidad_correccion - int(corr_usada.get(f.alumno, 0)), cap_e[f.alumno])
            else:
                cap = 1
            if cap <= 0:
                continue
            red.arista(("E", f.alumno), h, cap, 0)
            capa_h.add(h)
        aristas[f.id_postulacion] = red.arista(h, ("C", f.seccion), 1, costo_arista(f, p))

    usados = {red.nombres[red.dst[i]] for i in aristas.values()}
    for s, fila in secciones.iterrows():
        libres = int(fila.cupos) - int(cubiertos.get(s, 0))
        if ("C", s) in usados:
            for _ in range(libres):  # una arista por cupo
                red.arista(("C", s), "T", 1, 0)
    return red, aristas


def _pasada(post, secciones, p, horarios, pasada, previas=None):
    red, aristas = construir_red(post, secciones, p, horarios, pasada, previas)
    flujo, costo = red.resolver("S", "T")
    elegidas = [i for i, a in aristas.items() if red.flujo(a) > 0]
    asign = post[post["id_postulacion"].isin(elegidas)].assign(pasada=pasada)
    return asign, {"flujo": flujo, "costo_red": costo, "nodos": len(red.nombres),
                   "aristas": len(red.dst) // 2}


def resolver(post, secciones, p, horarios=None):
    """Flujo máximo de costo mínimo (una o dos pasadas según el modo)."""
    t0 = time.perf_counter()
    asign, info = _pasada(post, secciones, p, horarios, 1)
    info["flujo_pasada_1"] = info["flujo"]
    if p.modo_no_elegibles == "dos_pasadas":
        extra, info2 = _pasada(post, secciones, p, horarios, 2, previas=asign)
        asign = pd.concat([asign, extra])
        info["flujo_pasada_2"] = info2["flujo"]
        info["flujo"] += info2["flujo"]
        info["costo_red"] += info2["costo_red"]
    info["segundos"] = time.perf_counter() - t0
    return asign.copy(), info


def greedy_por_seccion(post, secciones, p, horarios=None):
    """Línea base (Alternativa 1 de la Entrega 1): cada sección, por separado y
    en orden, toma al mejor del ranking del profesor que todavía tenga
    capacidad y el bloque libre. Elegibles primero; no elegibles solo si el
    modo lo permite."""
    horarios = horarios or {}
    carga, corr, ocupados, elegidas = {}, {}, set(), []
    for s, fila in secciones.sort_index().iterrows():
        cand = post[post["seccion"] == s].assign(_ne=lambda d: ~d["elegible"].astype(bool))
        cand = cand.sort_values(["_ne", "rank_profe_ef"])
        libres = int(fila.cupos)
        bloque = horarios.get(s, CORR)
        for f in cand.itertuples():
            if libres == 0:
                break
            if not any(arista_permitida(f, p, k) for k in (1, 2)):
                continue
            if carga.get(f.alumno, 0) >= tope(f.alumno, p):
                continue
            if bloque == CORR:
                if corr.get(f.alumno, 0) >= p.capacidad_correccion:
                    continue
                corr[f.alumno] = corr.get(f.alumno, 0) + 1
            elif (f.alumno, bloque) in ocupados:
                continue
            ocupados.add((f.alumno, bloque))
            carga[f.alumno] = carga.get(f.alumno, 0) + 1
            elegidas.append(f.id_postulacion)
            libres -= 1
    return post[post["id_postulacion"].isin(elegidas)].copy()


def historico(post):
    return post[post["elegido_historico"]].copy()


def a_tabla(asign, secciones):
    cols = ["seccion", "sigla", "curso", "tipo", "alumno", "prio_profe", "rank_profe_ef", "prio_alumno",
            "orden_defecto", "nota", "promedio", "elegible", "P_O", "P_E", "P_A", "total_postulaciones"]
    cols += [c for c in ("pasada",) if c in asign]
    extra = [c for c in ("unidad", "bloque", "profesor") if c in secciones]
    t = asign[cols].join(secciones[extra], on="seccion")
    return t.sort_values(["sigla", "tipo", "seccion"]).reset_index(drop=True)


def no_cubiertas(asign, secciones):
    cubiertas = asign.groupby("seccion").size()
    sec = secciones[secciones["cupos"] > 0].copy()
    sec["asignados"] = cubiertas.reindex(sec.index, fill_value=0)
    return sec[sec["asignados"] < sec["cupos"]]


def decision_manual(post, asign, secciones, p):
    """Cupos sin cubrir y sus candidatos (elegibles o no), para que el
    Secretario decida a mano. Ordenados por el costo sin penalización."""
    sin = no_cubiertas(asign, secciones)
    cand = post[post["seccion"].isin(sin.index)].copy()
    carga = asign.groupby("alumno").size()
    cand["ayudantias_asignadas"] = cand["alumno"].map(carga).fillna(0).astype(int)
    cand["tope"] = cand["alumno"].map(lambda a: tope(a, p))
    cand["costo"] = (p.a * cand["P_O"] + p.b * cand["P_E"] + p.c * cand["P_A"]).round(3)
    cand["motivo"] = [
        "no elegible" if not e else ("sin capacidad" if n >= k else "tope horario")
        for e, n, k in zip(cand["elegible"], cand["ayudantias_asignadas"], cand["tope"])]
    cols = ["seccion", "sigla", "tipo", "alumno", "elegible", "cumple_promedio", "cumple_nota", "promedio",
            "nota", "rank_profe_ef", "prio_alumno", "costo", "ayudantias_asignadas", "tope", "motivo"]
    t = cand[cols].join(secciones[[c for c in ("unidad", "bloque") if c in secciones]], on="seccion")
    sin_cand = sin.index.difference(cand["seccion"])
    vacias = pd.DataFrame({"seccion": sin_cand, "motivo": "sin postulantes"})
    vacias = vacias.join(secciones[[c for c in ("sigla", "tipo", "unidad", "bloque") if c in secciones]],
                         on="seccion")
    return pd.concat([t.sort_values(["seccion", "costo"]), vacias], ignore_index=True)
