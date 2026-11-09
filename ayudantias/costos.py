"""Costo de la arista H -> C:  c_ij = a·P^O + b·P^E + c·P^A + d·[no elegible].

Las tres preferencias son rankings normalizados a [0, 1] (0 = primera opción,
1 = última), así son comparables y, con a + b + c + d = 1, el costo de toda
arista queda en [0, 1]:

  P^O  oferta: posición del alumno en el ranking del profesor de la sección.
       Si el profesor no rankeó a algunos (o a nadie), esos postulantes van
       después de los rankeados, en el orden por defecto (P^A).
  P^E  estudiante: prioridad que el alumno le dio a esta postulación dentro
       de todas las suyas.
  P^A  asignatura: orden por defecto de la sección, por nota del ramo y luego
       promedio general (de mayor a menor).

Elegible: promedio general >= promedio_minimo y nota del ramo >= nota_minima_ramo
(nota faltante no descalifica), salvo que el archivo de elegibilidad diga otra cosa.
"""
import pandas as pd

ESCALA = 1000  # los costos se redondean a enteros (milésimas) para el SSP


def _normalizar(rango, maximo):
    """(r - 1) / (R - 1), con 0 cuando la lista tiene un solo elemento."""
    den = (maximo - 1).where(maximo > 1)
    return ((rango - 1) / den).fillna(0.0).clip(0, 1)


def orden_por_defecto(post):
    """Posición de cada postulante en su sección por nota del ramo y promedio."""
    nota = post["nota"].fillna(post["promedio"])
    orden = post.assign(_n=nota).sort_values(["seccion", "_n", "promedio", "prio_alumno"],
                                             ascending=[True, False, False, True])
    return orden.groupby("seccion").cumcount().add(1).reindex(post.index)


def rank_profe_efectivo(post, orden_def):
    """Ranking del profesor; los no rankeados quedan al final, en el orden por defecto."""
    r = post["prio_profe"]
    max_rk = r.groupby(post["seccion"]).transform("max").fillna(0)
    sin = r.isna()
    pos_sin = orden_def.where(sin).groupby(post["seccion"]).rank(method="first")
    return r.where(~sin, max_rk + pos_sin)


def leer_elegibilidad_manual(ruta):
    """CSV con columnas alumno, elegible_manual (SI / NO / vacío)."""
    if not ruta:
        return {}
    df = pd.read_csv(ruta, dtype=str).fillna("")
    valores = {}
    for alumno, v in zip(df["alumno"], df["elegible_manual"]):
        v = v.strip().upper()
        if v in ("SI", "SÍ", "S", "1", "TRUE"):
            valores[alumno] = True
        elif v in ("NO", "N", "0", "FALSE"):
            valores[alumno] = False
        elif v:
            raise ValueError(f"elegible_manual inválido para {alumno}: {v!r} (use SI, NO o vacío)")
    return valores


def anotar(post, p):
    """Agrega a las postulaciones las columnas que usa el modelo."""
    post = post.copy()
    post["orden_defecto"] = orden_por_defecto(post)
    post["rank_profe_ef"] = rank_profe_efectivo(post, post["orden_defecto"])
    por_sec = post.groupby("seccion")
    post["P_O"] = _normalizar(post["rank_profe_ef"], por_sec["rank_profe_ef"].transform("max"))
    post["P_E"] = _normalizar(post["prio_alumno"], post.groupby("alumno")["prio_alumno"].transform("max"))
    post["P_A"] = _normalizar(post["orden_defecto"], por_sec["orden_defecto"].transform("max"))

    post["cumple_promedio"] = post["promedio"] >= p.promedio_minimo
    post["cumple_nota"] = post["nota"].isna() | (post["nota"] >= p.nota_minima_ramo)
    post["elegible_calculado"] = post["cumple_promedio"] & post["cumple_nota"]
    manual = leer_elegibilidad_manual(p.archivo_elegibilidad)
    post["elegible"] = [manual.get(a, e) for a, e in zip(post["alumno"], post["elegible_calculado"])]
    post["rankeado"] = post["prio_profe"].notna()
    return post


def costo_unitario(f, p, penalizar=True):
    """Costo en [0, 1] de asignar la postulación f (fila de `anotar`)."""
    c = p.a * f.P_O + p.b * f.P_E + p.c * f.P_A
    if penalizar and not f.elegible:
        c += p.d
    return c


def costo_arista(f, p):
    """Costo entero de la arista H -> C."""
    return round(ESCALA * costo_unitario(f, p, penalizar=p.modo_no_elegibles == "penalizar"))


def arista_permitida(f, p, pasada=1):
    """Restricciones duras a nivel de postulación (si no se cumplen, no hay arista)."""
    if not f.rankeado and not p.incluir_no_rankeados:
        return False
    if p.modo_no_elegibles == "excluir":
        return bool(f.elegible)
    if p.modo_no_elegibles == "dos_pasadas":
        return bool(f.elegible) == (pasada == 1)
    return True  # penalizar
