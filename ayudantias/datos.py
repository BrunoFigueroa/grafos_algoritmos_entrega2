"""Carga de postulaciones y reconstrucción de secciones.

El Excel anonimizado no trae el número de sección, pero sí "Postulantes en la
sección (mismo tipo)". Para un mismo (sigla, tipo, N) hay exactamente k·N
filas, es decir, k secciones de N postulantes. Se reparten las filas entre
las k secciones respetando:
  - un alumno aparece a lo más una vez por sección,
  - el ranking del profesor no se repite dentro de una sección,
  - a lo más un "Elegido" por sección (1 ayudante por sección y tipo).
"""
import random

import pandas as pd

COLUMNAS = {
    "ID anónimo": "alumno",
    "Sigla": "sigla",
    "Curso": "curso",
    "Tipo ayudante": "tipo",
    "Nota en el ramo": "nota",
    "Promedio general": "promedio",
    "Ranking del alumno": "prio_alumno",
    "Total postulaciones del alumno": "total_postulaciones",
    "Ranking del profesor": "prio_profe",
    "Postulantes en la sección (mismo tipo)": "n_seccion",
    "Estado": "estado",
}

DIAS = ["Lu", "Ma", "Mi", "Ju", "Vi"]
BLOQUES_POR_DIA = 7


def cargar_postulaciones(ruta):
    df = pd.read_excel(ruta).rename(columns=COLUMNAS)
    df["elegido_historico"] = df["estado"].eq("Elegido")
    df = df.reset_index(names="id_postulacion")
    df["seccion"] = reconstruir_secciones(df)
    return df


def reconstruir_secciones(df):
    secciones = pd.Series(index=df.index, dtype=object)
    for (sigla, tipo, n), grupo in df.groupby(["sigla", "tipo", "n_seccion"]):
        k = len(grupo) // n
        if len(grupo) % n:
            raise ValueError(f"{sigla} {tipo} N={n}: {len(grupo)} filas no es múltiplo de N")
        reparto = _repartir(grupo, k, n)
        for idx, s in reparto.items():
            secciones[idx] = f"{sigla}-{tipo[:3].upper()}-N{n:02d}-{s + 1}"
    return secciones


def _repartir(grupo, k, n):
    if k == 1:
        return {idx: 0 for idx in grupo.index}
    # primero los alumnos con más filas en el grupo (más restringidos)
    veces = grupo["alumno"].map(grupo["alumno"].value_counts())
    filas = grupo.assign(_v=veces).sort_values(["_v", "elegido_historico"], ascending=False)
    filas = list(filas[["alumno", "prio_profe", "elegido_historico"]].itertuples())
    for limitar_elegidos in (True, False):
        estado = {
            "tam": [0] * k,
            "alumnos": [set() for _ in range(k)],
            "ranks": [set() for _ in range(k)],
            "eleg": [0] * k,
        }
        asignado = {}
        if _backtrack(filas, 0, k, n, estado, asignado, limitar_elegidos):
            return asignado
    raise ValueError(f"No se pudo reconstruir secciones para {grupo.iloc[0][['sigla', 'tipo', 'n_seccion']].tolist()}")


def _backtrack(filas, i, k, n, e, asignado, limitar_elegidos):
    if i == len(filas):
        return True
    f = filas[i]
    rank = None if pd.isna(f.prio_profe) else f.prio_profe
    for s in range(k):
        if (e["tam"][s] >= n or f.alumno in e["alumnos"][s]
                or (rank is not None and rank in e["ranks"][s])
                or (limitar_elegidos and f.elegido_historico and e["eleg"][s] >= 1)):
            continue
        e["tam"][s] += 1
        e["alumnos"][s].add(f.alumno)
        if rank is not None:
            e["ranks"][s].add(rank)
        e["eleg"][s] += f.elegido_historico
        asignado[f.Index] = s
        if _backtrack(filas, i + 1, k, n, e, asignado, limitar_elegidos):
            return True
        e["tam"][s] -= 1
        e["alumnos"][s].discard(f.alumno)
        e["ranks"][s].discard(rank)
        e["eleg"][s] -= f.elegido_historico
        del asignado[f.Index]
    return False


def tabla_secciones(df, modo_cupos="historico", oferta=None, semilla=0):
    """Una fila por sección con su capacidad (cupos).

    Con `oferta` (ver cargar_oferta) cada sección reconstruida se vincula a una
    unidad real de la programación (bloque horario, profesor) y se agregan las
    unidades ofertadas que no recibieron postulantes.
    """
    sec = df.groupby("seccion").agg(
        sigla=("sigla", "first"),
        curso=("curso", "first"),
        tipo=("tipo", "first"),
        postulantes=("alumno", "size"),
        rankeados=("prio_profe", "count"),
        elegidos_historico=("elegido_historico", "sum"),
    )
    sec["unidad"] = None
    if oferta is not None:
        sec = _vincular_oferta(sec, oferta, semilla)
    if modo_cupos == "historico":
        sec["cupos"] = (sec["elegidos_historico"] > 0).astype(int)
    elif modo_cupos == "todas":
        sec["cupos"] = (sec["rankeados"] > 0).astype(int)
    elif modo_cupos == "oferta":
        if oferta is None:
            raise ValueError("el modo de cupos 'oferta' requiere la programación académica")
        # toda unidad ofertada demanda un ayudante; las secciones de postulación
        # sin par en la oferta conservan el criterio "todas"
        sec["cupos"] = (sec["unidad"].notna() | (sec["rankeados"] > 0)).astype(int)
    else:
        raise ValueError(f"modo de cupos desconocido: {modo_cupos}")
    return sec


# ---------------------------------------------------------------------------
# Programación académica (SAP): "Horarios Ing_inf.xls"
# ---------------------------------------------------------------------------

def _bloque(horario):
    """'MI 11:30 - 12:50' -> 'MI 11:30' (bloques estándar de 80 min)."""
    partes = horario.split()
    return f"{partes[0]} {partes[1]}"


def cargar_oferta(ruta, prefijo="CIT"):
    """Unidades que demandan ayudante, una fila por (unidad, tipo).

    - Cátedra: un ayudante por evento AYUDANTÍA distinto. En cursos con
      laboratorio dos secciones SAP comparten cátedra y ayudantía ("MADRE"),
      por eso la unidad es el evento y no la sección SAP. Bloque = el de la ayudantía.
    - Corrector: mismo grupo que la cátedra; sin bloque (corrige fuera de horario).
      Si el curso no tiene ayudantía, un corrector por sección SAP.
    - Laboratorio: un ayudante por evento LABORATORIO. Bloque = el del laboratorio.
    """
    h = pd.read_excel(ruta).dropna(how="all")
    h = h[h["Asignatura"].str.startswith(prefijo)].copy()
    h["evento"] = h["Descrip. Evento"].str.replace(r"\s*\d+$", "", regex=True)
    filas = []
    for sigla, g in h.groupby("Asignatura"):
        curso = g["Nombre Asig."].iloc[0]
        catedra = g[g["evento"].str.startswith("CÁTEDRA")]
        ayud = g[g["evento"].str.startswith("AYUDANTÍA")]
        grupos = ayud.groupby("Descrip. Evento")
        for evento, e in grupos:
            num = evento.split()[-1]
            secs = sorted(e["Sección"].unique())
            prof = catedra[catedra["Sección"].isin(secs)]["Profesor"].dropna()
            base = dict(sigla=sigla, curso=curso, secciones_sap=", ".join(secs),
                        profesor=prof.iloc[0] if len(prof) else None)
            filas.append(dict(base, unidad=f"{sigla}-CAT-G{num}", tipo="Cátedra",
                              bloque=_bloque(e["Horario"].iloc[0])))
            filas.append(dict(base, unidad=f"{sigla}-COR-G{num}", tipo="Corrector", bloque=None))
        if not len(ayud):
            for s, e in g.groupby("Sección"):
                prof = e["Profesor"].dropna()
                filas.append(dict(sigla=sigla, curso=curso, secciones_sap=s,
                                  profesor=prof.iloc[0] if len(prof) else None,
                                  unidad=f"{sigla}-COR-S{s.split()[-1]}", tipo="Corrector",
                                  bloque=None))
        for evento, e in g[g["evento"].str.startswith("LABORATORIO")].groupby("Descrip. Evento"):
            prof = e["Profesor"].dropna()
            filas.append(dict(sigla=sigla, curso=curso,
                              secciones_sap=", ".join(sorted(e["Sección"].unique())),
                              profesor=prof.iloc[0] if len(prof) else None,
                              unidad=f"{sigla}-LAB-{evento.split()[-1]}", tipo="Laboratorio",
                              bloque=_bloque(e["Horario"].iloc[0])))
    return pd.DataFrame(filas).set_index("unidad")


def _vincular_oferta(sec, oferta, semilla):
    """Empareja secciones reconstruidas con unidades reales del mismo (sigla, tipo).

    Los datos anonimizados no permiten saber qué sección reconstruida es qué
    grupo real, así que el emparejamiento es aleatorio (reproducible con
    `semilla`); el análisis de robustez repite el modelo con muchas semillas.
    """
    rng = random.Random(semilla)
    sec = sec.copy()
    vacias = []
    for (sigla, tipo), unidades in oferta.groupby(["sigla", "tipo"]):
        propias = sorted(sec.index[(sec["sigla"] == sigla) & (sec["tipo"] == tipo)])
        ids = list(unidades.index)
        rng.shuffle(ids)
        for s, u in zip(propias, ids):
            sec.at[s, "unidad"] = u
        for u in ids[len(propias):]:
            vacias.append(dict(unidades.loc[u, ["sigla", "curso", "tipo"]], seccion=u, unidad=u,
                               postulantes=0, rankeados=0, elegidos_historico=0))
    if vacias:
        sec = pd.concat([sec, pd.DataFrame(vacias).set_index("seccion")])
    info = oferta[["bloque", "profesor", "secciones_sap"]]
    sec = sec.join(info, on="unidad")
    sec["en_oferta"] = sec["unidad"].notna()
    return sec


def horarios_de_oferta(secciones):
    """Bloque horario por sección (solo las que tienen bloque en la oferta)."""
    b = secciones["bloque"].dropna()
    return dict(zip(b.index, b))


def horarios_sinteticos(secciones, semilla=0):
    """Escenario de prueba: cada sección en un bloque de 80 min al azar."""
    rng = random.Random(semilla)
    bloques = [f"{d}-{b}" for d in DIAS for b in range(1, BLOQUES_POR_DIA + 1)]
    return {s: rng.choice(bloques) for s in sorted(secciones)}

