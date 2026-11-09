"""Métricas de evaluación (Sección 8 de la Entrega 1, adaptadas al modelo final)."""
from .costos import costo_unitario
from .modelo import tope


def calcular(asign, secciones, p, horarios=None):
    """`asign` debe venir de postulaciones anotadas (costos.anotar)."""
    horarios = horarios or {}
    cupos = int(secciones["cupos"].sum())
    habilitada = secciones["cupos"].reindex(asign["seccion"]).fillna(0).to_numpy() > 0
    validas = asign[habilitada]
    carga = asign.groupby("alumno").size()
    topes = carga.index.map(lambda a: tope(a, p))
    con_bloque = asign[asign["seccion"].isin(horarios)]
    choques = (con_bloque.assign(b=con_bloque["seccion"].map(horarios))
               .groupby(["alumno", "b"]).size())
    rp = asign["rank_profe_ef"]
    n = len(asign)
    return {
        "cupos": cupos,
        "cubiertos": len(validas),
        "% cobertura": round(100 * len(validas) / cupos, 1) if cupos else 0.0,
        "alumnos distintos": int(carga.size),
        "alumnos con 1": int((carga == 1).sum()),
        "alumnos con 2": int((carga == 2).sum()),
        "alumnos con 3+": int((carga >= 3).sum()),
        "excesos de tope": int((carga > topes).sum()),
        "choques horarios": int((choques > 1).sum()),
        "no elegibles asignados": int((~asign["elegible"].astype(bool)).sum()),
        "no rankeados asignados": int((~asign["rankeado"].astype(bool)).sum()),
        "% 1a prio profe": round(100 * (rp == 1).mean(), 1) if n else 0.0,
        "% dentro de 3 del profe": round(100 * (rp <= 3).mean(), 1) if n else 0.0,
        "prio profe promedio": round(rp.mean(), 2) if n else 0.0,
        "% 1a prio alumno": round(100 * (asign["prio_alumno"] == 1).mean(), 1) if n else 0.0,
        "prio alumno promedio": round(asign["prio_alumno"].mean(), 2) if n else 0.0,
        "% 1o por notas": round(100 * (asign["orden_defecto"] == 1).mean(), 1) if n else 0.0,
        "P_O promedio": round(asign["P_O"].mean(), 3) if n else 0.0,
        "P_E promedio": round(asign["P_E"].mean(), 3) if n else 0.0,
        "P_A promedio": round(asign["P_A"].mean(), 3) if n else 0.0,
        "costo (misma función)": round(sum(costo_unitario(f, p) for f in asign.itertuples()), 2),
    }
