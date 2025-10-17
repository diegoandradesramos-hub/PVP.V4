
import streamlit as st
import pandas as pd
import numpy as np
import os, yaml, io, re
from PIL import Image

try:
    import pdfplumber
    PDF_OK = True
except Exception:
    PDF_OK = False

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

st.set_page_config(page_title="PVP La Terraza V4", page_icon="🍽️", layout="wide")
st.title("PVP La Terraza V4")

@st.cache_data
def load_csv(name):
    p = os.path.join(DATA_DIR, name)
    if os.path.exists(p):
        return pd.read_csv(p)
    return pd.DataFrame()

@st.cache_data
def load_settings():
    with open(os.path.join(DATA_DIR, "settings.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def norm(s):
    if pd.isna(s): return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

SET = load_settings()
currency = SET.get("currency_symbol","€")

ingredients = load_csv("ingredient_yields.csv")
category_margins = load_csv("category_margins.csv")
recipes = load_csv("recipes.csv")
recipe_lines = load_csv("recipe_lines.csv")
purchases = load_csv("purchases.csv")

with st.sidebar:
    st.header("Márgenes por sección")
    category_margins = st.data_editor(category_margins, num_rows="dynamic", use_container_width=True, key="cm")
    st.session_state["category_margins"] = category_margins
    overhead = st.number_input("Overhead por ración (€)", 0.0, 50.0, 0.00, 0.10, format="%.2f")

st.markdown("### 1) Subir compras (foto/PDF)")
uploaded = st.file_uploader("JPG/PNG/PDF. Si es PDF y no se lee, añade líneas manualmente.", type=["jpg","jpeg","png","pdf"], accept_multiple_files=True)

def add_purchase_row(rows, supplier, date, invoice_no, iva_rate, ingr, qty, unit, total, notes=""):
    rows.append({"date":date,"supplier":supplier,"ingredient":ingr,"qty":qty,"unit":unit,"total_cost_gross":total,"iva_rate":iva_rate,"invoice_no":invoice_no,"notes":notes})

new_rows = []
if uploaded:
    for f in uploaded:
        supplier=""; date=""; invoice_no=""; iva_rate=0.10
        if f.name.lower().endswith(".pdf") and PDF_OK:
            try:
                import io as _io
                with pdfplumber.open(_io.BytesIO(f.read())) as pdf:
                    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                if "21%" in text: iva_rate=0.21
                elif "10%" in text: iva_rate=0.10
            except Exception:
                pass
        with st.expander(f"Carga: {f.name}"):
            col1,col2,col3,col4 = st.columns(4)
            supplier = col1.text_input("Proveedor", supplier, key=f"supp_{f.name}")
            date = col2.text_input("Fecha (DD/MM/AAAA)", "", key=f"date_{f.name}")
            invoice_no = col3.text_input("Nº factura", "", key=f"inv_{f.name}")
            iva_rate = col4.number_input("IVA aplicado", 0.0, 0.30, float(iva_rate), 0.01, key=f"iva_{f.name}", format="%.2f")
            st.caption("Añade líneas (ingrediente, cantidad, unidad, total con IVA)")
            ingr = st.text_input("Ingrediente", key=f"ing_{f.name}")
            qty = st.number_input("Cantidad", 0.0, 1e6, 1.0, 0.1, key=f"qty_{f.name}")
            unit = st.text_input("Unidad (kg, L, unit)", "kg", key=f"unit_{f.name}")
            total = st.number_input("Total con IVA (€)", 0.0, 1e9, 0.0, 0.1, key=f"tot_{f.name}")
            if st.button(f"Añadir línea {f.name}"):
                add_purchase_row(new_rows, supplier, date, invoice_no, iva_rate, ingr, qty, unit, total)

if new_rows:
    purchases = pd.concat([purchases, pd.DataFrame(new_rows)], ignore_index=True)
    purchases.to_csv(os.path.join(DATA_DIR, "purchases.csv"), index=False, encoding="utf-8")

st.subheader("Compras registradas")
st.dataframe(purchases, use_container_width=True)

st.markdown("### 2) Ingredientes (mermas)")
ingredients = st.data_editor(ingredients, num_rows="dynamic", use_container_width=True, key="ingr")
ingredients.to_csv(os.path.join(DATA_DIR, "ingredient_yields.csv"), index=False, encoding="utf-8")

st.markdown("### 3) Productos por sección")
recipes = st.data_editor(recipes, num_rows="dynamic", use_container_width=True, key="rec")
recipes.to_csv(os.path.join(DATA_DIR, "recipes.csv"), index=False, encoding="utf-8")

st.markdown("### 4) Recetas (BOM por producto)")
recipe_lines = st.data_editor(recipe_lines, num_rows="dynamic", use_container_width=True, key="bom")
recipe_lines.to_csv(os.path.join(DATA_DIR, "recipe_lines.csv"), index=False, encoding="utf-8")

st.markdown("### 5) Costes netos (ajustados por merma)")

def compute_cost_helper(purchases, yields):
    if purchases.empty:
        return pd.DataFrame(columns=["ingredient","unit","unit_cost_net","usable_yield","effective_cost"])
    df = purchases.copy()
    df["unit_cost_net"] = df["total_cost_gross"] / (1.0 + df["iva_rate"].fillna(0.10)) / df["qty"].replace(0,np.nan)
    df["_k_ing"] = df["ingredient"].astype(str).str.strip().str.lower().str.replace(r"\s+"," ",regex=True)
    df["_k_unit"] = df["unit"].astype(str).str.strip().str.lower().str.replace(r"\s+"," ",regex=True)
    y = yields.copy()
    y["_k_ing"] = y["ingredient"].astype(str).str.strip().str.lower().str.replace(r"\s+"," ",regex=True)
    y["_k_unit"] = y["unit"].astype(str).str.strip().str.lower().str.replace(r"\s+"," ",regex=True)
    last = df.sort_index().groupby(["_k_ing","_k_unit"]).last(numeric_only=True).reset_index()
    r = last.merge(y[["_k_ing","_k_unit","usable_yield"]], on=["_k_ing","_k_unit"], how="left")
    r["usable_yield"] = r["usable_yield"].fillna(1.0)
    r["effective_cost"] = r["unit_cost_net"] / r["usable_yield"].replace(0,np.nan)
    r["ingredient"] = r["_k_ing"]; r["unit"] = r["_k_unit"]
    return r[["ingredient","unit","unit_cost_net","usable_yield","effective_cost"]]

helper = compute_cost_helper(purchases, ingredients)
st.dataframe(helper, use_container_width=True)

st.markdown("### 6) PVP sugerido")

def pricing_table(recipes, lines, helper, cat_margins, overhead):
    cost_map = {(row["ingredient"], row["unit"]): row["effective_cost"] for _,row in helper.iterrows()}
    cm = {str(r["category"]): float(r["target_margin"]) for _,r in cat_margins.iterrows() if pd.notna(r["target_margin"])}
    rows = []
    for _, r in recipes.iterrows():
        item_key = r["item_key"]
        iva = float(r.get("iva_rate", 0.10)) if pd.notna(r.get("iva_rate", np.nan)) else 0.10
        margin = None
        if pd.notna(r.get("target_margin", np.nan)) and str(r.get("target_margin")).strip()!="":
            try: margin = float(r["target_margin"])
            except: margin = None
        if margin is None:
            margin = cm.get(r["category"], 0.70)
        item_lines = lines[lines["item_key"]==item_key]
        cost_ing = 0.0; missing = False
        for _, ln in item_lines.iterrows():
            k = (str(ln["ingredient"]).strip().lower(), str(ln["unit"]).strip().lower())
            c = cost_map.get(k, np.nan)
            if pd.isna(c):
                missing = True; continue
            cost_ing += c * float(ln["qty_per_portion"])
        cost_total = cost_ing + overhead
        price_excl = cost_total/(1.0 - margin) if (1.0 - margin) > 0 else np.nan
        pvp = price_excl*(1.0 + iva) if pd.notna(price_excl) else np.nan
        rows.append({
            "Sección": r["category"],
            "Producto": r["display_name"],
            "IVA": f"{iva*100:.0f}%",
            "Margen": f"{margin*100:.0f}%",
            "Coste ingr.": cost_ing,
            "Overhead": overhead,
            "Coste total": cost_total,
            "Precio sin IVA": price_excl,
            "PVP": pvp,
            "Faltan costes": "Sí" if missing else ""
        })
    return pd.DataFrame(rows)

pr = pricing_table(recipes, recipe_lines, helper, st.session_state["category_margins"], overhead)
if helper.empty:
    st.info("Sube compras para ver PVP con costes reales.")
else:
    mcols = ["Coste ingr.","Overhead","Coste total","Precio sin IVA","PVP"]
    show = pr.copy()
    for c in mcols:
       show[c] = show[c].map(lambda x: f"{x:.2f}{currency}" if pd.notna(x) else "")
    st.dataframe(show.sort_values([\"Sección\",\"Producto\"]), use_container_width=True)
