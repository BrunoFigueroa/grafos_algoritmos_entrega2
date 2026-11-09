"""Robustez frente al emparejamiento sección reconstruida <-> grupo real.

El emparejamiento no es identificable con los datos anonimizados, así que se
resuelve el modelo para muchas semillas y se reporta la distribución de cada
métrica por método.
"""
import pandas as pd

from . import datos, metricas, modelo

CLAVES = ["% cobertura", "alumnos distintos", "alumnos con 3+", "choques horarios",
          "no elegibles asignados", "P_O promedio", "P_E promedio", "P_A promedio",
          "costo (misma función)"]


def analizar(post, p, oferta, semillas):
    """`post` anotado (costos.anotar)."""
    filas = []
    hist = modelo.historico(post)
    for s in semillas:
        sec = datos.tabla_secciones(post, p.cupos, oferta, semilla=s)
        hor = datos.horarios_de_oferta(sec)
        metodos = {
            "Histórico (manual)": hist,
            "Greedy por sección": modelo.greedy_por_seccion(post, sec, p, hor),
            "Flujo costo mínimo": modelo.resolver(post, sec, p, hor)[0],
        }
        for nombre, a in metodos.items():
            m = metricas.calcular(a, sec, p, hor)
            filas.append({"semilla": s, "método": nombre, **{k: m[k] for k in CLAVES}})
    df = pd.DataFrame(filas)
    resumen = df.groupby("método")[CLAVES].agg(["mean", "min", "max"]).round(3)
    return df, resumen
