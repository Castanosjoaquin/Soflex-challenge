"""EDA del dataset del challenge Soflex (n=30).

Uso:
  uv run --no-project --with pandas --with matplotlib --with seaborn --with tabulate \
      python docs/research/eda/scripts/eda.py

Escribe tablas en scripts/_out/*.md / *.csv y figuras en figures/*.png.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from common import (
    CAT_ORDER, FIG_DIR, OUT_DIR, PRIO_COLORS, PRIO_ORDER, caller_text, jaccard, load,
    md_table, norm, split_answer, split_pipe, strip_accents, tokens,
)

sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams.update({"figure.dpi": 130, "savefig.bbox": "tight", "savefig.facecolor": "white"})

df = load()
REPORT: list[str] = []


def out(title: str, body) -> None:
    if isinstance(body, pd.DataFrame | pd.Series):
        body = md_table(body if isinstance(body, pd.DataFrame) else body.to_frame())
    REPORT.append(f"\n### {title}\n\n{body}\n")
    print(f"\n### {title}\n{body}")


def save(fig, name):
    fig.savefig(FIG_DIR / name)
    plt.close(fig)


CAT_SHORT = {
    "INCENDIO_RESCATE": "Incendio/Rescate",
    "ACCIDENTE_VIAL": "Accidente vial",
    "EMERGENCIA_MEDICA": "Emerg. médica",
    "DEFENSA_CIVIL": "Defensa civil",
    "SERVICIOS_PUBLICOS": "Serv. públicos",
    "CONVIVENCIA_SEGURIDAD": "Convivencia/Seg.",
}
df["cat"] = pd.Categorical(df["categoria"], CAT_ORDER, ordered=True)
df["comuna"] = df["barrio_comuna"].str.extract(r"Comuna (\d+)").astype(int)
df["barrio"] = df["barrio_comuna"].str.replace(r"\s*\(Comuna \d+\)", "", regex=True)

# ---------------------------------------------------------------- 0. calidad básica
out("Nulos por columna", df.isna().sum().rename("nulos").to_frame().T)
out("Cardinalidad por columna", df.drop(columns=["ts", "cat"]).nunique().rename("únicos").to_frame().T)

# ---------------------------------------------------------------- 1. composición
for col in ["categoria", "prioridad_sugerida", "origen_reporte", "barrio", "comuna"]:
    out(f"Distribución de {col}", df[col].value_counts().rename("n").to_frame())

ct_cp = pd.crosstab(df["cat"], df["prioridad_sugerida"]).reindex(columns=["P1", "P2", "P3"])
out("Categoría × prioridad", ct_cp)
ct_sc = pd.crosstab(df["origen_reporte"], df["cat"])
out("Origen × categoría", ct_sc)
ct_sp = pd.crosstab(df["origen_reporte"], df["prioridad_sugerida"])
out("Origen × prioridad", ct_sp)
ct_cc = pd.crosstab(df["cat"], df["comuna"])
out("Categoría × comuna", ct_cc)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
ax = axes[0, 0]
vc = df["cat"].value_counts().reindex(CAT_ORDER)
ax.barh([CAT_SHORT[c] for c in vc.index], vc.values, color="#5d6d7e")
ax.invert_yaxis(); ax.set_title("Casos por categoría"); ax.set_xlabel("casos")
ax = axes[0, 1]
vc = df["prioridad_sugerida"].value_counts().reindex(PRIO_ORDER, fill_value=0)
ax.bar(vc.index, vc.values, color=[PRIO_COLORS[p] for p in vc.index])
for i, v in enumerate(vc.values):
    ax.text(i, v + 0.2, str(v), ha="center")
ax.set_title("Casos por prioridad (no hay P4)"); ax.set_ylabel("casos")
ax = axes[1, 0]
vc = df["origen_reporte"].value_counts()
ax.barh(vc.index, vc.values, color="#5d6d7e"); ax.invert_yaxis()
ax.set_title("Casos por origen del reporte"); ax.set_xlabel("casos")
ax = axes[1, 1]
vc = df["comuna"].value_counts().sort_index()
ax.bar([f"C{c}" for c in vc.index], vc.values, color="#5d6d7e")
ax.set_title("Casos por comuna (CABA)"); ax.set_ylabel("casos")
fig.suptitle("Composición del dataset (n=30)", fontsize=14, weight="bold")
fig.tight_layout()
save(fig, "01_composicion.png")

fig, axes = plt.subplots(1, 2, figsize=(14, 4.8), gridspec_kw={"width_ratios": [1, 1.4]})
sns.heatmap(ct_cp.rename(index=CAT_SHORT), annot=True, fmt="d", cmap="Reds", cbar=False, ax=axes[0])
axes[0].set_title("Categoría × prioridad"); axes[0].set_xlabel("prioridad"); axes[0].set_ylabel("")
sns.heatmap(ct_sc.rename(columns=CAT_SHORT), annot=True, fmt="d", cmap="Blues", cbar=False, ax=axes[1])
axes[1].set_title("Origen × categoría"); axes[1].set_xlabel(""); axes[1].set_ylabel("")
plt.setp(axes[1].get_xticklabels(), rotation=30, ha="right")
fig.tight_layout()
save(fig, "02_cruces.png")

# ---------------------------------------------------------------- 2. tiempo
df = df.sort_values("ts").reset_index(drop=True)
df["gap_min"] = df["ts"].diff().dt.total_seconds() / 60
df["hora"] = df["ts"].dt.hour
out("Rango temporal", f"{df.ts.min()} → {df.ts.max()} ({(df.ts.max()-df.ts.min())})")
out("¿ID ordenado igual que timestamp?", str((df["n"].diff().dropna() == 1).all()))
out("Gaps entre llamadas (min)", df["gap_min"].describe().round(1).to_frame().T)
out("Llamadas por día", df["ts"].dt.date.value_counts().sort_index().rename("n").to_frame())
out("Gaps > 2h", df.loc[df.gap_min > 120, ["id_registro", "timestamp_llamada", "gap_min"]])

# saludo del operador vs hora
def saludo(t):
    t = strip_accents(t.lower())
    for k in ["buen dia", "buenas tardes", "buenas noches"]:
        if k in t:
            return k
    return None


df["saludo"] = df["transcripcion_cruda"].map(saludo)
expected = lambda h: "buen dia" if 6 <= h < 13 else ("buenas tardes" if 13 <= h < 20 else "buenas noches")
inc = df[df.saludo.notna() & (df.saludo != df.hora.map(expected))]
out("Saludos inconsistentes con la hora", inc[["id_registro", "timestamp_llamada", "saludo"]])

fig, axes = plt.subplots(2, 1, figsize=(13, 6.5), gridspec_kw={"height_ratios": [2, 1]})
ax = axes[0]
ypos = {c: i for i, c in enumerate(CAT_ORDER)}
for p in ["P1", "P2", "P3"]:
    s = df[df.prioridad_sugerida == p]
    ax.scatter(s.ts, s.categoria.map(ypos), s=90, color=PRIO_COLORS[p], label=p, edgecolor="k", zorder=3)
ax.set_yticks(range(len(CAT_ORDER))); ax.set_yticklabels([CAT_SHORT[c] for c in CAT_ORDER])
ax.set_title("Línea de tiempo de llamadas (color = prioridad)"); ax.legend(title="prioridad", ncol=3)
ax = axes[1]
ax.bar(df.ts, df.gap_min.fillna(0), width=0.02, color="#5d6d7e")
ax.set_ylabel("min desde la\nllamada anterior"); ax.set_title("Intervalo entre llamadas consecutivas")
fig.tight_layout()
save(fig, "03_tiempo.png")

# ---------------------------------------------------------------- 3. transcripciones
T = df["transcripcion_cruda"]
df["chars"] = T.str.len()
df["palabras"] = T.str.split().str.len()
df["turnos"] = T.str.count(r"(?:Operador|Llamante):")
df["turnos_llamante"] = T.str.count(r"Llamante:")
df["pal_llamante"] = T.map(caller_text).str.split().str.len()
df["exclam"] = T.str.count("!")
df["oraciones_llamante"] = T.map(caller_text).str.count(r"[.!?](?:\s|$)")
out("Longitud de transcripciones", df[["chars", "palabras", "pal_llamante", "turnos", "oraciones_llamante"]].describe().round(1))
out("Turnos por transcripción", df.turnos.value_counts().rename("n").to_frame())
out("Palabras del llamante por categoría", df.groupby("cat", observed=True).pal_llamante.agg(["mean", "min", "max"]).round(1))
out("Palabras del llamante y '!' por prioridad", df.groupby("prioridad_sugerida").agg(pal=("pal_llamante", "mean"), exclam_media=("exclam", "mean"), con_exclam=("exclam", lambda s: (s > 0).sum()), n=("exclam", "size")).round(2))

# apertura del operador por origen
df["apertura_op"] = T.str.extract(r"Operador:\s*(.*?)\s*Llamante:")[0]
out("Apertura del operador por origen", df[["id_registro", "origen_reporte", "apertura_op"]].sort_values("origen_reporte"))

LUNFARDO = {
    "mirá": r"\bmirá\b", "nene / chicos / chico": r"\b(nene|chicos?)\b", "colectivo": r"\bcolectivo",
    "se trabó / trabando": r"\btrab(ó|ando)\b", "picando (la vereda)": r"\bpicando\b",
    "está que arde": r"que arde", "blanca como un papel": r"como un papel", "a chorros": r"a chorros",
    "mordió el guardarraíl": r"mordió", "se prendió fuego / prendieron": r"prendi(ó|eron)",
    "bodegón": r"bodegón", "fútbol 5": r"fútbol 5", "camperas": r"campera", "monopatín": r"monopat",
    "canil": r"\bcanil\b", "delivery": r"\bdelivery\b", "mano a Provincia": r"mano a provincia",
    "bajada (de autopista)": r"\bbajada\b", "bajo puente / bajo nivel": r"bajo (puente|nivel)",
    "cordón cuneta": r"cordón cuneta", "vereda": r"\bvereda\b", "una tipa (árbol)": r"\btipa\b",
    "3ro C (piso/depto)": r"\d+(ro|do|to|mo|vo|no)\s+[A-Z]\b", "trifásica": r"trifásica",
    "dogo / pitbull": r"dogo|pitbull", "Belgrano R": r"Belgrano R\b",
}
lun = []
for k, pat in LUNFARDO.items():
    hits = df.loc[T.str.contains(pat, case=False, regex=True), "id_registro"].str[-3:].tolist()
    lun.append({"expresión": k, "casos": len(hits), "ids": ", ".join(hits)})
lun = pd.DataFrame(lun).sort_values("casos", ascending=False)
out("Regionalismos / coloquialismos detectados", lun.set_index("expresión"))

NOISE = {
    "signos '!'": r"!", "muletilla 'mirá/bueno/che/eh'": r"\b(mirá|bueno|che|eh|este\.\.\.)\b",
    "puntos suspensivos": r"\.\.\.", "palabra repetida consecutiva": r"\b(\w+)\s+\1\b",
    "pedido de urgencia (por favor/urgente/auxilio/ya)": r"por favor|urgente|auxilio|\bya!",
    "duda del llamante (o / como / unos)": r"\b(o bicicleta|como dos|unos \d+|de unos)\b",
    "marca de [inaudible]/corte": r"\[|inaudible|se corta",
}
noise = []
for k, pat in NOISE.items():
    c = T.str.contains(pat, case=False, regex=True)
    noise.append({"marcador": k, "casos": int(c.sum())})
out("Marcadores de ruido/estrés", pd.DataFrame(noise).set_index("marcador"))

ADDR = {
    "número directo 'Calle 1234'": r"[A-ZÁÉÍÓÚ][\wáéíóúñ.]+(?:\s[\wáéíóúñ.]+){0,3}\s\d{3,5}\b",
    "'al 800' (altura redondeada)": r"\bal \d{3,5}\b",
    "'casi X' (esquina cercana)": r"\bcasi [A-ZÁÉÍÓÚ]",
    "'entre X y Y'": r"\bentre [A-ZÁÉÍÓÚ][\wáéíóú. ]+ y [A-ZÁÉÍÓÚ]",
    "intersección 'X y Y' (sin número)": r"\b(?:en|de) (?:la esquina de )?(?:Av\. )?[A-ZÁÉÍÓÚ][\wáéíóú.]+(?: [A-Z0-9][\wáéíóú.]+)* y (?:Av\. )?[A-ZÁÉÍÓÚ]",
    "'esquina'": r"\besquina\b",
    "'altura' / 'a la altura'": r"\baltura\b",
    "prefijo 'Av.'": r"\bAv\.",
    "landmark (parque/plaza/estación/subestación/rotonda/viaducto/puente/autopista)": r"\b(Parque|Plaza|estación|subestación|rotonda|viaducto|puente|Autopista)\b",
    "menciona barrio": r"\b(Soldati|Balvanera|San Cristóbal|Barracas|Belgrano)\b",
    "piso/depto": r"\bpisos? \d|\d+(ro|do|to)\s+[A-Z]\b",
}
addr = []
for k, pat in ADDR.items():
    c = T.str.contains(pat, regex=True)
    addr.append({"patrón": k, "casos": int(c.sum()), "ids": ", ".join(df.loc[c, "id_registro"].str[-3:])})
out("Cómo se expresan las direcciones", pd.DataFrame(addr).set_index("patrón"))

fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
sns.stripplot(data=df, y=df.cat.map(CAT_SHORT), x="pal_llamante", hue="prioridad_sugerida",
              palette=PRIO_COLORS, size=9, jitter=0.15, ax=axes[0], order=[CAT_SHORT[c] for c in CAT_ORDER])
axes[0].set_xlabel("palabras del llamante"); axes[0].set_ylabel(""); axes[0].set_title("Largo del relato por categoría")
axes[0].legend(title="prioridad")
lun_top = lun[lun.casos > 0].head(14)
axes[1].barh(lun_top["expresión"], lun_top["casos"], color="#5d6d7e"); axes[1].invert_yaxis()
axes[1].set_title("Regionalismos / coloquialismos (casos)"); axes[1].set_xlabel("casos")
fig.tight_layout()
save(fig, "04_transcripciones.png")

# señales de keywords por categoría (c-TF-IDF simple)
GENERIC = {"hola", "avenida", "puede", "dos", "anos", "quedo", "arriba", "cerca", "casi", "altura", "juan", "salguero", "nadie", "esta"}
doc_tok = df["transcripcion_cruda"].map(lambda t: tokens(caller_text(t), stem=0))
cat_counter = {c: Counter() for c in CAT_ORDER}
for c, toks in zip(df.categoria, doc_tok):
    cat_counter[c].update(set(toks))
df_cnt = Counter()
for toks in doc_tok:
    df_cnt.update(set(toks))
rows = []
for c in CAT_ORDER:
    ncat = (df.categoria == c).sum()
    scores = {w: (k / ncat) * (k / df_cnt[w]) for w, k in cat_counter[c].items()
              if k >= 2 and w not in GENERIC}
    top = sorted(scores, key=scores.get, reverse=True)[:8]
    rows.append({"categoría": c, "términos en ≥2 casos de la categoría (n_cat/n_total)": ", ".join(f"{w} ({cat_counter[c][w]}/{df_cnt[w]})" for w in top) or "—"})
out("Términos característicos por categoría (aparece en n_cat casos de la categoría / n_total casos del dataset)", pd.DataFrame(rows).set_index("categoría"))

P1_SIGNALS = {
    "personas atrapadas/adentro": r"atrapad|quedó adentro|debajo del|adentro",
    "no respira/no responde/inconsciente": r"no respira|no responde|no le entra el aire|no se mueve|inconscien",
    "menores/vulnerables": r"\bnene|niña|hija|chicos|embarazada|82 años|escuela",
    "fuego/explosión/humo": r"fuego|explot|explosión|humo|llamas|llamarada",
    "gas/combustible/eléctrico": r"\bgas\b|gasoil|nafta|cable|chispe|eléctric|litio",
    "exclamación": r"!",
}
sig = []
CT = T.map(caller_text)
for k, pat in P1_SIGNALS.items():
    c = CT.str.contains(pat, case=False, regex=True)
    row = {"señal": k}
    for p in ["P1", "P2", "P3"]:
        m = df.prioridad_sugerida == p
        row[p] = f"{int((c & m).sum())}/{int(m.sum())}"
    sig.append(row)
out("Señales léxicas vs prioridad (casos con la señal / total de la prioridad)", pd.DataFrame(sig).set_index("señal"))

# ---------------------------------------------------------------- 4. grounding de etiquetas
def ground_street(label: str, text: str) -> str:
    if not label or label.lower().startswith("s/n"):
        return "n/a"
    lab_core = re.sub(r"\s*\(.*?\)", "", label).strip()
    if lab_core in text:
        return "literal"
    nt, nl = norm(text), norm(lab_core)
    nl_noav = re.sub(r"^(avenida|autopista|bajada|puente) ", "", nl)
    if nl in nt or (nl_noav and re.search(rf"\b{re.escape(nl_noav)}\b", nt)):
        return "normalizado"
    toks = [t for t in nl_noav.split() if len(t) > 2 and t not in {"avenida", "general"}]
    if toks and sum(re.search(rf"\b{re.escape(t)}\b", nt) is not None for t in toks) / len(toks) >= 0.5:
        return "parcial"
    return "ausente"


def ground_altura(label: str, text: str) -> str:
    num = re.match(r"^\s*(\d{2,5})\b", label)
    if not num:
        return "no numérica"
    n = num.group(1)
    if re.search(rf"\b{n}\b", text):
        return "literal" + (" (+anotación)" if "(" in label else "")
    return "inferida" + (" (esquina)" if "esquina" in label else "")


g_rows = []
for _, r in df.iterrows():
    t = r.transcripcion_cruda
    inters = [s.strip() for s in re.split(r"\s+y\s+|\s*/\s*", r.interseccion_detectada) if s.strip()]
    inter_g = [ground_street(s, t) for s in inters]
    barrio_in = norm(r.barrio) in norm(t)
    g_rows.append({
        "id": r.id_registro[-3:], "calle_detectada": r.calle_detectada, "g_calle": ground_street(r.calle_detectada, t),
        "altura_detectada": r.altura_detectada, "g_altura": ground_altura(r.altura_detectada, t),
        "interseccion_detectada": r.interseccion_detectada,
        "g_inter": " / ".join(f"{s}:{g}" for s, g in zip(inters, inter_g)),
        "inter_calles": len(inters), "inter_presentes": sum(g in {"literal", "normalizado", "parcial"} for g in inter_g),
        "barrio_en_texto": barrio_in, "comuna_en_texto": bool(re.search(r"comuna", t, re.I)),
    })
G = pd.DataFrame(g_rows)
G.to_csv(OUT_DIR / "grounding_ubicacion.csv", index=False)
out("Grounding de ubicación (detalle por caso)", G.drop(columns=["inter_calles", "inter_presentes"]).set_index("id"))
out("Grounding calle (resumen)", G.g_calle.value_counts().rename("casos").to_frame())
out("Grounding altura (resumen)", G.g_altura.value_counts().rename("casos").to_frame())
inter_sum = pd.Series({
    "calles de intersección etiquetadas": int(G.inter_calles.sum()),
    "presentes en el texto (literal/normalizado/parcial)": int(G.inter_presentes.sum()),
    "casos con TODAS las calles de intersección en el texto": int((G.inter_presentes == G.inter_calles).sum()),
    "casos con al menos una calle inventada/inferida": int((G.inter_presentes < G.inter_calles).sum()),
    "casos con barrio mencionado en el texto": int(G.barrio_en_texto.sum()),
    "casos con comuna mencionada en el texto": int(G.comuna_en_texto.sum()),
})
out("Grounding intersección / barrio / comuna (resumen)", inter_sum.rename("valor").to_frame())

# respuestas del relato
a_rows = []
for _, r in df.iterrows():
    tt = set(tokens(r.transcripcion_cruda))
    for item in split_pipe(r.preguntas_respondidas_en_relato):
        q, a = split_answer(item)
        at = tokens(a)
        cov = (sum(t in tt for t in at) / len(at)) if at else float("nan")
        a_rows.append({"id": r.id_registro[-3:], "pregunta": q, "respuesta": a, "cobertura_tokens": round(cov, 2)})
A = pd.DataFrame(a_rows)
A["nivel"] = pd.cut(A.cobertura_tokens, [-0.01, 0.34, 0.67, 1.0], labels=["baja (<1/3): parafraseo/inferencia", "media", "alta (≥2/3): casi literal"])
A.to_csv(OUT_DIR / "grounding_respuestas.csv", index=False)
out("Grounding de respuestas (cobertura de tokens de la respuesta en la transcripción)", A.cobertura_tokens.describe().round(2).to_frame().T)
out("Grounding de respuestas por nivel", A.nivel.value_counts().rename("respuestas").to_frame())
out("Respuestas con menor cobertura (top 10)", A.sort_values("cobertura_tokens").head(10).set_index("id"))

fig, axes = plt.subplots(1, 3, figsize=(15, 4.3))
order_g = ["literal", "normalizado", "parcial", "ausente", "n/a"]
colors_g = {"literal": "#1e8449", "normalizado": "#52be80", "parcial": "#f4d03f", "ausente": "#c0392b", "n/a": "#bdc3c7"}
vc = G.g_calle.value_counts().reindex(order_g, fill_value=0)
axes[0].bar(vc.index, vc.values, color=[colors_g[k] for k in vc.index]); axes[0].set_title("calle_detectada vs transcripción")
alt_order = ["literal", "literal (+anotación)", "inferida (esquina)", "inferida", "no numérica"]
alt_col = ["#1e8449", "#52be80", "#c0392b", "#e74c3c", "#bdc3c7"]
vc = G.g_altura.value_counts().reindex(alt_order, fill_value=0)
axes[1].bar(range(len(vc)), vc.values, color=alt_col); axes[1].set_xticks(range(len(vc)))
axes[1].set_xticklabels(vc.index, rotation=25, ha="right"); axes[1].set_title("altura_detectada vs transcripción")
pres = int(G.inter_presentes.sum()); tot = int(G.inter_calles.sum())
axes[2].bar(["en el texto", "no está en el texto"], [pres, tot - pres], color=["#1e8449", "#c0392b"])
axes[2].set_title(f"Calles de intersección etiquetadas (n={tot})")
for a in axes:
    a.set_ylabel("casos / calles")
fig.suptitle("¿Las etiquetas de ubicación están ancladas en el texto?", fontsize=13, weight="bold")
fig.tight_layout()
save(fig, "05_grounding_ubicacion.png")

# ---------------------------------------------------------------- 5. preguntas de protocolo
p_rows, link_rows = [], []
SIM_T = 0.25
for _, r in df.iterrows():
    M = split_pipe(r.preguntas_protocolo_mandatorias)
    R = [split_answer(x)[0] for x in split_pipe(r.preguntas_respondidas_en_relato)]
    P = split_pipe(r.preguntas_pendientes)
    Mt = [tokens(q) for q in M]
    exact_R = sum(q in M for q in R)
    exact_P = sum(q in M for q in P)
    def best(q):
        return max((jaccard(tokens(q), m), i) for i, m in enumerate(Mt))
    fuzzy_R = [best(q) for q in R]
    fuzzy_P = [best(q) for q in P]
    covered = {i for s, i in fuzzy_R + fuzzy_P if s >= SIM_T}
    p_rows.append({
        "id": r.id_registro[-3:], "cat": r.categoria, "mandatorias": len(M), "respondidas": len(R), "pendientes": len(P),
        "resp_exacta_en_mand": exact_R, "pend_exacta_en_mand": exact_P,
        "resp_fuzzy_en_mand": sum(s >= SIM_T for s, _ in fuzzy_R), "pend_fuzzy_en_mand": sum(s >= SIM_T for s, _ in fuzzy_P),
        "mand_sin_estado": len(M) - len(covered),
    })
    for q, (s, i) in zip(R, fuzzy_R):
        link_rows.append({"id": r.id_registro[-3:], "tipo": "respondida", "pregunta": q, "mandatoria_más_parecida": M[i], "jaccard": round(s, 2)})
    for q, (s, i) in zip(P, fuzzy_P):
        link_rows.append({"id": r.id_registro[-3:], "tipo": "pendiente", "pregunta": q, "mandatoria_más_parecida": M[i], "jaccard": round(s, 2)})
PQ = pd.DataFrame(p_rows)
L = pd.DataFrame(link_rows)
PQ.to_csv(OUT_DIR / "protocolo_por_caso.csv", index=False)
L.to_csv(OUT_DIR / "protocolo_links.csv", index=False)
out("Conteo de preguntas por caso", PQ[["mandatorias", "respondidas", "pendientes"]].describe().round(2))
tot = pd.Series({
    "mandatorias (total)": PQ.mandatorias.sum(),
    "respondidas (total)": PQ.respondidas.sum(),
    "pendientes (total)": PQ.pendientes.sum(),
    "respondidas cuyo texto es EXACTAMENTE una mandatoria": PQ.resp_exacta_en_mand.sum(),
    "pendientes cuyo texto es EXACTAMENTE una mandatoria": PQ.pend_exacta_en_mand.sum(),
    f"respondidas con match difuso (Jaccard≥{SIM_T}) a una mandatoria": PQ.resp_fuzzy_en_mand.sum(),
    f"pendientes con match difuso (Jaccard≥{SIM_T}) a una mandatoria": PQ.pend_fuzzy_en_mand.sum(),
    "mandatorias que no figuran ni como respondidas ni como pendientes (difuso)": PQ.mand_sin_estado.sum(),
    "casos donde respondidas+pendientes cubre todas las mandatorias": int((PQ.mand_sin_estado == 0).sum()),
})
out("Consistencia mandatorias ↔ respondidas/pendientes", tot.rename("valor").to_frame())
out("Ejemplos de vínculo pregunta → mandatoria más parecida", L.sort_values("jaccard", ascending=False).head(12).set_index("id"))

# reutilización entre casos
allM = [(r.categoria, q) for _, r in df.iterrows() for q in split_pipe(r.preguntas_protocolo_mandatorias)]
cntM = Counter(q for _, q in allM)
out("Preguntas mandatorias únicas vs totales", f"{len(cntM)} únicas de {len(allM)} totales; repetidas literalmente: {sum(1 for v in cntM.values() if v > 1)}")
within, across = [], []
for i in range(len(allM)):
    for j in range(i + 1, len(allM)):
        s = jaccard(tokens(allM[i][1]), tokens(allM[j][1]))
        (within if allM[i][0] == allM[j][0] else across).append(s)
out("Similitud entre preguntas mandatorias (Jaccard de tokens)", pd.DataFrame({
    "misma categoría": pd.Series(within).describe().round(3), "distinta categoría": pd.Series(across).describe().round(3)}).T)
pairs = []
for i in range(len(allM)):
    for j in range(i + 1, len(allM)):
        s = jaccard(tokens(allM[i][1]), tokens(allM[j][1]))
        if s >= 0.3:
            pairs.append({"cat_a": allM[i][0], "a": allM[i][1], "cat_b": allM[j][0], "b": allM[j][1], "jaccard": round(s, 2)})
out("Pares de mandatorias más parecidas (Jaccard≥0.3)", pd.DataFrame(pairs).sort_values("jaccard", ascending=False).head(15).to_markdown(index=False) if pairs else "ninguno")

# temas de pregunta (intención) para catálogo canónico por categoría
THEMES = {
    "personas atrapadas / heridas / víctimas": r"atrapad|herid|lesionad|mordid|víctima|inconscien|ocupantes|personas",
    "conciencia / respiración / signos vitales": r"respira|conscien|conocimiento|habla|frases|hablar|vía (aérea|respiratoria)|pulso|asfixia|ubicado",
    "sangrado / lesión": r"sangr|lesion|fractur|acortamiento|golpe|quemadur",
    "gas / combustible / derrame": r"\bgas\b|garrafa|combustible|fluidos|derrame|nafta|líquido",
    "electricidad / cables": r"cable|eléctric|energía|tensión|transformador|chisp",
    "fuego / humo": r"fuego|humo|llama|calor|ignición",
    "propagación / linderos / evacuación": r"lindero|vivienda|evacu|desalo|asentamiento|propaga|vereda fue",
    "tránsito / carriles / vía": r"carril|tránsito|traza|avenida|clausurad|sendas",
    "estructura / colapso": r"estructura|socav|desnivel|viga|colapso|ensanch|cabina",
    "antecedentes / medicación": r"antecedentes|medicación|epipen|adrenalina|autoinyector|diabetes",
    "evolución (sigue/continúa/tiempo)": r"sigue|continúa|cuánto tiempo|ascendiendo",
    "armas": r"armas",
}
th = defaultdict(Counter)
unthemed = 0
for c, q in allM:
    hit = False
    for k, pat in THEMES.items():
        if re.search(pat, q, re.I):
            th[c][k] += 1
            hit = True
    unthemed += (not hit)
TH = pd.DataFrame(th).fillna(0).astype(int).reindex(columns=CAT_ORDER)
out("Temas de las preguntas mandatorias por categoría (# preguntas que tocan el tema)", TH)
out("Mandatorias sin tema asignado", str(unthemed))

fig, axes = plt.subplots(1, 2, figsize=(15, 5), gridspec_kw={"width_ratios": [1.3, 1]})
x = range(len(PQ))
axes[0].bar(x, PQ.mandatorias, color="#5d6d7e", label="mandatorias")
axes[0].bar(x, -PQ.respondidas, color="#1e8449", label="respondidas (en relato)")
axes[0].bar(x, -PQ.pendientes, bottom=-PQ.respondidas, color="#e67e22", label="pendientes")
axes[0].scatter(x, PQ.mand_sin_estado, color="#c0392b", zorder=3, label="mandatorias sin estado")
axes[0].axhline(0, color="k", lw=0.8)
axes[0].set_xticks(list(x)); axes[0].set_xticklabels(PQ.id, rotation=90, fontsize=8)
axes[0].set_title("Preguntas por caso (arriba: mandatorias; abajo: respondidas+pendientes)")
axes[0].legend(fontsize=8, loc="lower right"); axes[0].set_ylabel("# preguntas")
sns.heatmap(TH.rename(columns=CAT_SHORT), annot=True, fmt="d", cmap="Greens", cbar=False, ax=axes[1])
axes[1].set_title("Temas de preguntas mandatorias × categoría"); plt.setp(axes[1].get_xticklabels(), rotation=30, ha="right")
fig.tight_layout()
save(fig, "06_protocolo.png")

# ---------------------------------------------------------------- 6. instrucciones / riesgos / recursos
I = df["instrucciones_prearribo"]
df["instr_oraciones"] = I.str.count(r"[.!](?:\s|$)")
df["instr_palabras"] = I.str.split().str.len()
df["instr_mayus"] = I.str.contains(r"\b[A-ZÁÉÍÓÚ]{4,}\s+[A-ZÁÉÍÓÚ]{2,}")
df["instr_neg"] = I.str.count(r"\b(No|no|NO|NUNCA|Prohibido|PROHIBIDO|BAJO NINGUNA)\b")
out("Instrucciones pre-arribo: estructura", df[["instr_oraciones", "instr_palabras", "instr_neg"]].describe().round(1))
out("Instrucciones con énfasis en MAYÚSCULAS", df.loc[df.instr_mayus, ["id_registro", "categoria", "instrucciones_prearribo"]].set_index("id_registro"))
iw, ia = [], []
for i in range(30):
    for j in range(i + 1, 30):
        s = jaccard(tokens(I[i]), tokens(I[j]))
        (iw if df.categoria[i] == df.categoria[j] else ia).append(s)
out("Similitud entre instrucciones (Jaccard)", pd.DataFrame({"misma cat": pd.Series(iw).describe().round(3), "distinta cat": pd.Series(ia).describe().round(3)}).T)

INSTR_THEMES = {
    "no tocar/no mover a la víctima": r"no mover|no intente (pararla|forzar)|no intentar (tirar|enderezar)|retire el casco|no moverlo",
    "alejarse / perímetro / evacuar": r"evacu|perímetro|alej|manténgase|metros|desalo|vereda de enfrente|acera de enfrente",
    "no usar agua": r"agua (común|bajo)|con agua|no arrojar agua|arrojar agua",
    "fuentes de ignición (fumar, llaves, motores)": r"fumar|cigarrillo|llaves de luz|motores|timbres",
    "cortar tránsito / balizar": r"tránsito|balizas|conos|circulación",
    "posición del paciente": r"sentar|sentado|piernas|lateral|Trendelenburg|erguida",
    "abrigar / contener": r"abrig|calma|conten",
    "cortar energía / gas": r"electricidad|batería|llave de contacto|apagar el motor|corte",
    "no intervenir / resguardarse": r"no intervenga|resgu",
}
it = pd.DataFrame({k: I.str.contains(p, case=False, regex=True) for k, p in INSTR_THEMES.items()})
it["cat"] = df.categoria
out("Temas de instrucciones pre-arribo por categoría", it.groupby("cat").sum().T.reindex(columns=CAT_ORDER))

# riesgos
Rk = df["riesgos_detectados"].str.split(r",\s*")
df["n_riesgos"] = Rk.str.len()
out("Riesgos por caso", df.n_riesgos.describe().round(2).to_frame().T)
allr = Counter(norm(x) for xs in Rk for x in xs)
out("Riesgos repetidos literalmente entre casos", str({k: v for k, v in allr.items() if v > 1}) or "ninguno")

# recursos
RES_PATTERNS = {
    "SAME / ambulancia": r"SAME|Ambulancia",
    "Bomberos (autobomba/dotación/cisterna)": r"Bomber|Autobomba|Dotación|Cisterna",
    "Rescate (unidad/móvil)": r"Rescate",
    "Policía / comisaría / patrullero / vallado": r"Polic|Comisar|Patrull|Vallado|custodia",
    "Tránsito (móvil/agentes/grúa)": r"Tránsito|Grúa",
    "Distribuidora eléctrica (Edenor/Edesur)": r"Edenor|Edesur",
    "Gas (Metrogas)": r"Metrogas",
    "Agua (AySA)": r"AySA",
    "Autopistas (AUSA)": r"AUSA",
    "Defensa Civil / Guardia de Auxilio": r"Defensa Civil|Guardia de Auxilio",
    "Otros (arbolado, trenes, zoonosis, semaforización, arquitectos)": r"Arbolado|Trenes|Animal|Semaforizaci|Arquitect|Balizamiento",
}
Res = df["recursos_recomendados_despacho"]
rr = pd.DataFrame({k: Res.str.contains(p, regex=True) for k, p in RES_PATTERNS.items()})
rr["cat"] = df.categoria; rr["prio"] = df.prioridad_sugerida
out("Recursos por categoría (# casos que los piden)", rr.groupby("cat").sum(numeric_only=True).T.reindex(columns=CAT_ORDER))
out("Recursos por prioridad (# casos que los piden)", rr.groupby("prio").sum(numeric_only=True).T)
df["n_items_recursos"] = Res.str.split(r"\s*\+\s*").str.len()
df["unidades"] = Res.map(lambda s: sum(int(m) for m in re.findall(r"(\d+)x", s)) + len([p for p in re.split(r"\s*\+\s*", s) if not re.match(r"\s*\d+x", p)]))
out("Ítems de recurso por prioridad", df.groupby("prioridad_sugerida")[["n_items_recursos", "unidades"]].mean().round(2))
out("Formato de ítems de recurso", f"ítems con prefijo 'Nx': {sum(bool(re.match(r'\s*\d+x', p)) for s in Res for p in re.split(r'\s*\+\s*', s))} / {sum(len(re.split(r'\s*\+\s*', s)) for s in Res)}")

fig, axes = plt.subplots(1, 2, figsize=(15, 5), gridspec_kw={"width_ratios": [1.3, 1]})
sns.heatmap(rr.groupby("cat").sum(numeric_only=True).T.reindex(columns=CAT_ORDER).rename(columns=CAT_SHORT),
            annot=True, fmt="d", cmap="Blues", cbar=False, ax=axes[0])
axes[0].set_title("Recursos recomendados × categoría (# casos)"); plt.setp(axes[0].get_xticklabels(), rotation=30, ha="right")
sns.heatmap(it.groupby("cat").sum().T.reindex(columns=CAT_ORDER).rename(columns=CAT_SHORT),
            annot=True, fmt="d", cmap="Oranges", cbar=False, ax=axes[1])
axes[1].set_title("Temas de instrucción pre-arribo × categoría"); plt.setp(axes[1].get_xticklabels(), rotation=30, ha="right")
fig.tight_layout()
save(fig, "07_recursos_instrucciones.png")

# ---------------------------------------------------------------- 8. baseline BM25 leave-one-out
class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = docs; self.k1, self.b = k1, b
        self.avg = sum(map(len, docs)) / len(docs)
        self.df = Counter(t for d in docs for t in set(d)); self.N = len(docs)
        self.tf = [Counter(d) for d in docs]

    def score(self, q, i):
        s, d = 0.0, self.docs[i]
        for t in set(q):
            if t not in self.tf[i]:
                continue
            idf = math.log(1 + (self.N - self.df[t] + 0.5) / (self.df[t] + 0.5))
            f = self.tf[i][t]
            s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
        return s


docs = [tokens(caller_text(t)) for t in df.transcripcion_cruda]
res = []
for i in range(30):
    idx = [j for j in range(30) if j != i]
    bm = BM25([docs[j] for j in idx])
    sc = sorted(((bm.score(docs[i], k), idx[k]) for k in range(len(idx))), reverse=True)
    top1 = sc[0][1]
    top3 = [j for _, j in sc[:3]]
    vote = Counter(df.categoria[j] for j in top3).most_common(1)[0][0]
    pvote = Counter(df.prioridad_sugerida[j] for j in top3).most_common(1)[0][0]
    res.append({"id": df.id_registro[i][-3:], "real_cat": df.categoria[i], "top1_cat": df.categoria[top1], "top3_cat": vote,
                "real_p": df.prioridad_sugerida[i], "top1_p": df.prioridad_sugerida[top1], "top3_p": pvote,
                "vecino": df.id_registro[top1][-3:], "score": round(sc[0][0], 2)})
B = pd.DataFrame(res)
B.to_csv(OUT_DIR / "bm25_loo.csv", index=False)
acc = pd.Series({
    "categoría top-1": (B.real_cat == B.top1_cat).mean(), "categoría voto top-3": (B.real_cat == B.top3_cat).mean(),
    "categoría baseline mayoritaria": df.categoria.value_counts().iloc[0] / 30,
    "prioridad top-1": (B.real_p == B.top1_p).mean(), "prioridad voto top-3": (B.real_p == B.top3_p).mean(),
    "prioridad baseline mayoritaria (P1)": (df.prioridad_sugerida == "P1").mean(),
}).round(3)
out("BM25 leave-one-out (sobre texto del llamante)", acc.rename("accuracy").to_frame())
out("BM25 LOO: errores de categoría top-1", B[B.real_cat != B.top1_cat].set_index("id"))

# keyword-rule baseline sobre categoría (reglas simples, para ver techo de un mock)
RULES = [
    ("EMERGENCIA_MEDICA", r"ambulancia|SAME|desmay|convuls|alérgic|asma|broncoesp|fractura|paciente|cayó|tropezó|golpeó"),
    ("ACCIDENTE_VIAL", r"chocó|choque|colectivo|camión|moto|volc|autopista|guardarraíl|ciclovía"),
    ("INCENDIO_RESCATE", r"fuego|incendi|humo|llamas|explot|bomberos|ascensor|atrapad|quema"),
    ("DEFENSA_CIVIL", r"árbol|tipa|derrumb|marquesina|gas|inund|anega|viento|medianera"),
    ("SERVICIOS_PUBLICOS", r"semáforo|caño|pozo|socav|cable|agua potable"),
    ("CONVIVENCIA_SEGURIDAD", r"pelea|perro|robo|disturb|botellas|pitbull"),
]
def rule_cat(t):
    t = caller_text(t)
    sc = {c: len(re.findall(p, t, re.I)) for c, p in RULES}
    best = max(sc.values())
    return "?" if best == 0 else max(sc, key=sc.get)
df["rule_cat"] = df.transcripcion_cruda.map(rule_cat)
out("Reglas de keywords (diseñadas mirando el dataset → optimistas)", f"accuracy categoría = {(df.rule_cat == df.categoria).mean():.3f}")
out("Reglas: errores", df.loc[df.rule_cat != df.categoria, ["id_registro", "categoria", "rule_cat"]].set_index("id_registro"))

(OUT_DIR / "tablas.md").write_text("# Tablas generadas por eda.py\n" + "".join(REPORT), encoding="utf-8")
print("\nOK ->", OUT_DIR / "tablas.md")

# ---------------------------------------------------------------- 9. anotación manual: ¿la transcripción responde cada mandatoria?
# Anotación subjetiva hecha leyendo cada caso (A = respondida, P = parcial/implícita, N = no surge del relato).
MANUAL = {
    "001": "ANN", "002": "NPN", "003": "ANP", "004": "PNN", "005": "PAN", "006": "PNP", "007": "NNN",
    "008": "PNN", "009": "NNN", "010": "NNN", "011": "NNN", "012": "ANN", "013": "NAA", "014": "PNN",
    "015": "NNP", "016": "NPP", "017": "NPP", "018": "PNN", "019": "NNN", "020": "ANA", "021": "NPN",
    "022": "PNA", "023": "PNP", "024": "PNN", "025": "NAN", "026": "NNN", "027": "PNN", "028": "NPN",
    "029": "PNN", "030": "PNN",
}
man = []
for _, r in df.iterrows():
    k = r.id_registro[-3:]
    for q, code in zip(split_pipe(r.preguntas_protocolo_mandatorias), MANUAL[k]):
        man.append({"id": k, "cat": r.categoria, "prio": r.prioridad_sugerida, "mandatoria": q, "estado_manual": code})
MAN = pd.DataFrame(man)
MAN.to_csv(OUT_DIR / "mandatorias_anotacion_manual.csv", index=False)
lab = {"A": "respondida", "P": "parcial/implícita", "N": "no surge del relato"}
out("Anotación manual: estado de las 90 mandatorias según el relato", MAN.estado_manual.map(lab).value_counts().rename("preguntas").to_frame())
out("Anotación manual por categoría", pd.crosstab(MAN.cat, MAN.estado_manual.map(lab)).reindex(CAT_ORDER))
fig, ax = plt.subplots(figsize=(9, 4))
cm = pd.crosstab(MAN.cat, MAN.estado_manual).reindex(CAT_ORDER)[["A", "P", "N"]]
left = pd.Series(0, index=cm.index)
for code, col in zip(["A", "P", "N"], ["#1e8449", "#f4d03f", "#c0392b"]):
    ax.barh([CAT_SHORT[c] for c in cm.index], cm[code], left=left, color=col, label=lab[code])
    left += cm[code]
ax.invert_yaxis(); ax.set_xlabel("# preguntas mandatorias")
ax.set_title("¿El relato ya responde las preguntas mandatorias? (anotación manual, 90 preguntas)")
ax.legend(loc="lower right", fontsize=8)
fig.tight_layout()
save(fig, "08_checklist_manual.png")
(OUT_DIR / "tablas.md").write_text("# Tablas generadas por eda.py\n" + "".join(REPORT), encoding="utf-8")
