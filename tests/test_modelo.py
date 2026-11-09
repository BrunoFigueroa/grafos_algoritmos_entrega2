import json
import random
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from ayudantias import costos, datos, metricas, modelo
from ayudantias.config import Parametros
from ayudantias.flujo import RedFlujo

RAIZ = Path(__file__).parent.parent
XLSX = RAIZ / "postulaciones_ayudantias_anonimo.xlsx"
OFERTA = RAIZ / "Horarios Ing_inf.xls"


@pytest.fixture(scope="module")
def crudo():
    return datos.cargar_postulaciones(XLSX)


@pytest.fixture(scope="module")
def post(crudo):
    return costos.anotar(crudo, Parametros())


@pytest.fixture(scope="module")
def oferta():
    return datos.cargar_oferta(OFERTA)


def _post_chico(**cols):
    """Postulaciones sintéticas mínimas, ya anotadas."""
    base = {"id_postulacion": range(len(cols["alumno"])), "prio_alumno": 1, "total_postulaciones": 1,
            "nota": 6.0, "promedio": 6.0, "prio_profe": 1.0, "n_seccion": 1, "elegido_historico": False,
            "sigla": "CIT0000", "tipo": "Cátedra"}
    df = pd.DataFrame({**base, **cols})
    return costos.anotar(df, Parametros())


# --- algoritmo ----------------------------------------------------------------

def test_ejemplo_entrega1_optimo_global():
    # E1-C1: 95, E1-C2: 94, E2-C1: 90, E2-C2: 30  -> óptimo global 90 + 94 = 184
    val = {("E1", "C1"): 95, ("E1", "C2"): 94, ("E2", "C1"): 90, ("E2", "C2"): 30}
    red = RedFlujo()
    for e in ("E1", "E2"):
        red.arista("S", e, 1)
    for c in ("C1", "C2"):
        red.arista(c, "T", 1)
    idx = {k: red.arista(*k, 1, 100 - v) for k, v in val.items()}
    flujo, costo = red.resolver("S", "T")
    elegidas = {k for k, i in idx.items() if red.flujo(i)}
    assert flujo == 2
    assert elegidas == {("E1", "C2"), ("E2", "C1")}
    assert 200 - costo == 184


def _a_networkx(red):
    g = nx.DiGraph()
    for i in range(0, len(red.dst), 2):
        u, v = red.nombres[red.dst[i + 1]], red.nombres[red.dst[i]]
        cap = red.cap[i] + red.cap[i + 1]
        if g.has_edge(u, v):  # aristas paralelas C->T: nodo auxiliar
            u2 = ("aux", i)
            g.add_edge(u, u2, capacity=cap, weight=red.costo[i])
            g.add_edge(u2, v, capacity=cap, weight=0)
        else:
            g.add_edge(u, v, capacity=cap, weight=red.costo[i])
    return g


@pytest.mark.parametrize("semilla", range(5))
def test_coincide_con_networkx(post, semilla):
    rng = random.Random(semilla)
    a = rng.randint(0, 10) / 10
    b = rng.randint(0, 10 - round(a * 10)) / 10
    p = Parametros(cupos="todas").con_pesos(a + 0.01, b, 1 - a - b, d=rng.choice([0.0, 0.3, 0.6]))
    sec = datos.tabla_secciones(post, p.cupos)
    horarios = datos.horarios_sinteticos(sec.index, semilla) if semilla % 2 else None
    red, _ = modelo.construir_red(post, sec, p, horarios)
    g = _a_networkx(red)
    flujo, costo = red.resolver("S", "T")
    f_nx = nx.max_flow_min_cost(g, "S", "T")
    assert flujo == sum(f_nx["S"].values())
    assert costo == nx.cost_of_flow(g, f_nx)


def test_solo_hc_tiene_costo(post, oferta):
    """Guía: todas las aristas son capacidad con costo 0, salvo H -> C."""
    p = Parametros()
    sec = datos.tabla_secciones(post, p.cupos, oferta, 0)
    red, aristas = modelo.construir_red(post, sec, p, datos.horarios_de_oferta(sec))
    de_postulacion = set(aristas.values())
    for i in range(0, len(red.dst), 2):
        if i not in de_postulacion:
            assert red.costo[i] == 0
        else:
            assert red.nombres[red.dst[i + 1]][0] == "H" and red.nombres[red.dst[i]][0] == "C"


# --- parámetros y costos --------------------------------------------------------

def test_pesos_deben_sumar_uno():
    with pytest.raises(ValueError, match="debe ser 1"):
        Parametros(a=0.5, b=0.5, c=0.5)
    with pytest.raises(ValueError, match="no negativos"):
        Parametros(a=1.2, b=-0.2, c=0.0)
    with pytest.raises(ValueError, match="modo_no_elegibles"):
        Parametros(modo_no_elegibles="otro")


def test_json_entregado_es_valido(tmp_path):
    p = Parametros.desde_json(RAIZ / "parametros.json")
    assert abs(p.a + p.b + p.c + p.d - 1) < 1e-9
    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps({"pesos": {"a": 1, "b": 0, "c": 0, "d": 0}, "externas": {"P001": 2},
                                "capacidades": {"max_ayudantias": 2}, "clave_rara": 1}))
    with pytest.raises(ValueError, match="desconocidas"):
        Parametros.desde_json(ruta)


def test_preferencias_normalizadas(post):
    for col in ("P_O", "P_E", "P_A"):
        assert post[col].between(0, 1).all()
    # el 1° del profesor (y el 1° por notas) tienen penalización 0
    assert (post.loc[post["rank_profe_ef"] == 1, "P_O"] == 0).all()
    assert (post.loc[post["orden_defecto"] == 1, "P_A"] == 0).all()
    # todo costo en [0, 1] porque a + b + c + d = 1
    p = Parametros(a=0.3, b=0.2, c=0.3, d=0.2, modo_no_elegibles="penalizar")
    c = [costos.costo_unitario(f, p) for f in post.itertuples()]
    assert min(c) >= 0 and max(c) <= 1 + 1e-9


def test_orden_por_defecto_si_el_profe_no_rankea():
    post = _post_chico(alumno=["A", "B", "C"], seccion=["X"] * 3, prio_profe=[None, 1.0, None],
                       nota=[5.5, 6.0, 6.8], n_seccion=3)
    r = dict(zip(post["alumno"], post["rank_profe_ef"]))
    # B fue rankeado 1°; los no rankeados siguen, ordenados por nota (C antes que A)
    assert r == {"B": 1, "C": 2, "A": 3}
    assert dict(zip(post["alumno"], post["orden_defecto"])) == {"C": 1, "B": 2, "A": 3}


# --- restricciones duras --------------------------------------------------------

@pytest.mark.parametrize("cupos", ["historico", "todas"])
def test_restricciones_duras(post, cupos):
    p = Parametros(cupos=cupos)
    sec = datos.tabla_secciones(post, cupos)
    horarios = datos.horarios_sinteticos(sec.index, 3)
    asign, info = modelo.resolver(post, sec, p, horarios)
    assert info["flujo"] == len(asign)
    assert asign.groupby("alumno").size().max() <= p.max_ayudantias
    por_sec = asign.groupby("seccion").size()
    assert (por_sec <= sec["cupos"].reindex(por_sec.index)).all()
    bloques = asign["seccion"].map(horarios)
    assert not asign.assign(b=bloques).duplicated(["alumno", "b"]).any()


def test_capa_horaria_impide_tope():
    post = _post_chico(alumno=["A", "A"], seccion=["X", "Y"], prio_alumno=[1, 2])
    sec = pd.DataFrame({"cupos": [1, 1]}, index=["X", "Y"])
    p = Parametros()
    asign, _ = modelo.resolver(post, sec, p, horarios={"X": "Lu-1", "Y": "Lu-1"})
    assert len(asign) == 1
    asign, _ = modelo.resolver(post, sec, p, horarios={"X": "Lu-1", "Y": "Ma-1"})
    assert len(asign) == 2


@pytest.mark.parametrize("cap, esperado", [(1, 1), (2, 2), (3, 3)])
def test_bloque_ficticio_de_correccion(cap, esperado):
    """Sin horario, las postulaciones pasan por H_i,corr con capacidad `cap`."""
    post = _post_chico(alumno=["A"] * 4, seccion=list("WXYZ"), tipo="Corrector", prio_alumno=[1, 2, 3, 4])
    sec = pd.DataFrame({"cupos": [1] * 4}, index=list("WXYZ"))
    asign, _ = modelo.resolver(post, sec, Parametros(capacidad_correccion=cap))
    assert len(asign) == esperado  # nunca más que max_ayudantias = 3
    assert set(asign["prio_alumno"]) == set(range(1, esperado + 1))


def test_cupos_multiples_crean_aristas():
    post = _post_chico(alumno=["A", "B", "C"], seccion=["X"] * 3, prio_profe=[1.0, 2.0, 3.0], n_seccion=3)
    sec = pd.DataFrame({"cupos": [2]}, index=["X"])
    red, _ = modelo.construir_red(post, sec, Parametros())
    a_t = [i for i in range(0, len(red.dst), 2) if red.nombres[red.dst[i]] == "T"]
    assert len(a_t) == 2 and all(red.cap[i] == 1 for i in a_t)
    asign, _ = modelo.resolver(post, sec, Parametros())
    assert set(asign["alumno"]) == {"A", "B"}


def test_externas_reducen_tope(post):
    p = Parametros()
    sec = datos.tabla_secciones(post)
    asign, _ = modelo.resolver(post, sec, p)
    alumno = asign["alumno"].value_counts().index[0]
    asign2, _ = modelo.resolver(post, sec, p.con(externas={alumno: p.max_ayudantias}))
    assert alumno not in set(asign2["alumno"])


# --- no elegibles ------------------------------------------------------------------

def _caso_no_elegible():
    # X: solo postula B (no elegible). Y: A (elegible) y B.
    post = _post_chico(alumno=["B", "A", "B"], seccion=["X", "Y", "Y"], prio_profe=[1.0, 2.0, 1.0],
                       promedio=[4.0, 6.0, 4.0], n_seccion=[1, 2, 2], prio_alumno=[1, 1, 2])
    sec = pd.DataFrame({"cupos": [1, 1]}, index=["X", "Y"])
    return post, sec


def test_modo_excluir():
    post, sec = _caso_no_elegible()
    asign, _ = modelo.resolver(post, sec, Parametros(modo_no_elegibles="excluir"))
    assert list(asign["alumno"]) == ["A"]
    manual = modelo.decision_manual(post, asign, sec, Parametros())
    assert set(manual.loc[manual["seccion"] == "X", "motivo"]) == {"no elegible"}


def test_dos_pasadas_no_desplaza_elegibles():
    post, sec = _caso_no_elegible()
    asign, info = modelo.resolver(post, sec, Parametros(modo_no_elegibles="dos_pasadas"))
    assert info["flujo_pasada_1"] == 1 and info["flujo_pasada_2"] == 1
    assert dict(zip(asign["seccion"], asign["alumno"])) == {"Y": "A", "X": "B"}
    assert dict(zip(asign["seccion"], asign["pasada"])) == {"Y": 1, "X": 2}


def test_penalizar_sin_d_ignora_elegibilidad():
    # Con d = 0 el no elegible B, 1° del profe en Y, puede ganarle a A
    post = _post_chico(alumno=["B", "A"], seccion=["Y", "Y"], prio_profe=[1.0, 2.0], promedio=[4.0, 6.0],
                       n_seccion=2)
    sec = pd.DataFrame({"cupos": [1]}, index=["Y"])
    p = Parametros(a=1.0, b=0.0, c=0.0, d=0.0, modo_no_elegibles="penalizar")
    assert list(modelo.resolver(post, sec, p)[0]["alumno"]) == ["B"]
    # con d > a, la penalización (0,6) supera la diferencia de ranking (0,4): gana A
    p = Parametros(a=0.4, b=0.0, c=0.0, d=0.6, modo_no_elegibles="penalizar")
    assert list(modelo.resolver(post, sec, p)[0]["alumno"]) == ["A"]


def test_con_pesos_reescala():
    p = Parametros().con_pesos(d=0.0)
    assert abs(p.a - 0.4) < 1e-6 and abs(p.b - 0.3) < 1e-6 and abs(p.c - 0.3) < 1e-6
    q = p.con_pesos(1, 1, 2, d=0.5)
    assert (q.a, q.b, q.c, q.d) == (0.125, 0.125, 0.25, 0.5)


def test_d_alto_usa_el_minimo_de_no_elegibles(post, oferta):
    """Con d alto un no elegible solo entra si ningún elegible puede cubrir el cupo:
    usa tantos como las dos pasadas (que es el mínimo) y cubre lo mismo o más."""
    sec = datos.tabla_secciones(post, "historico", oferta, 0)
    hor = datos.horarios_de_oferta(sec)
    base = Parametros()
    dos, _ = modelo.resolver(post, sec, base.con_pesos(d=0.0, modo_no_elegibles="dos_pasadas"), hor)
    for d in (0.6, 0.9):
        pen, _ = modelo.resolver(post, sec, base.con_pesos(d=d), hor)
        assert len(pen) >= len(dos)
        assert (~pen["elegible"]).sum() == (~dos["elegible"]).sum()


def test_elegibilidad_manual(tmp_path, crudo):
    p = Parametros()
    post = costos.anotar(crudo, p)
    alumno = post.loc[~post["elegible"], "alumno"].iloc[0]
    ruta = tmp_path / "eleg.csv"
    pd.DataFrame({"alumno": [alumno], "elegible_manual": ["SI"]}).to_csv(ruta, index=False)
    post2 = costos.anotar(crudo, p.con(archivo_elegibilidad=str(ruta)))
    assert post2.loc[post2["alumno"] == alumno, "elegible"].all()
    pd.DataFrame({"alumno": [alumno], "elegible_manual": ["quizás"]}).to_csv(ruta, index=False)
    with pytest.raises(ValueError, match="inválido"):
        costos.anotar(crudo, p.con(archivo_elegibilidad=str(ruta)))


# --- datos ----------------------------------------------------------------------------

def test_reconstruccion_secciones(post):
    g = post.groupby("seccion")
    assert (g.size() == g["n_seccion"].first()).all()
    assert not post.duplicated(["seccion", "alumno"]).any()
    rk = post.dropna(subset=["prio_profe"])
    assert not rk.duplicated(["seccion", "prio_profe"]).any()
    assert (g["elegido_historico"].sum() <= 1).all()


def test_oferta_unidades(oferta):
    assert oferta["sigla"].nunique() == 44
    # CIT2107: 7 secciones SAP con laboratorio comparten 4 cátedras "MADRE"
    c = oferta[oferta["sigla"] == "CIT2107"]["tipo"].value_counts()
    assert c["Cátedra"] == 4 and c["Laboratorio"] == 7
    assert oferta.loc[oferta["tipo"] == "Corrector", "bloque"].isna().all()
    assert oferta.loc[oferta["tipo"] != "Corrector", "bloque"].notna().all()


@pytest.mark.parametrize("semilla", [0, 1])
def test_vinculo_oferta(post, oferta, semilla):
    sec = datos.tabla_secciones(post, "oferta", oferta, semilla)
    assert not sec["unidad"].dropna().duplicated().any()
    assert set(oferta.index) <= set(sec["unidad"].dropna())
    v = sec[sec["postulantes"] > 0].dropna(subset=["unidad"])
    assert (oferta.loc[v["unidad"], "tipo"].to_numpy() == v["tipo"].to_numpy()).all()


@pytest.mark.parametrize("semilla", [0, 5])
def test_horarios_reales_sin_topes(post, oferta, semilla):
    p = Parametros(cupos="oferta")
    sec = datos.tabla_secciones(post, p.cupos, oferta, semilla)
    hor = datos.horarios_de_oferta(sec)
    asign, _ = modelo.resolver(post, sec, p, hor)
    m = metricas.calcular(asign, sec, p, hor)
    assert m["choques horarios"] == 0 and m["excesos de tope"] == 0
