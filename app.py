import streamlit as st
import pandas as pd

st.set_page_config(page_title="Mi Copiloto Financiero", page_icon="💰", layout="wide")
st.title("💰 Registro Rápido de Gastos")

if "transacciones" not in st.session_state:
    st.session_state.transacciones = []

# --- FORMULARIO RÁPIDO CON DESPLEGABLES Y BOTONES ---
st.subheader("⚡ Añadir nuevo movimiento")

col_cat, col_monto = st.columns([2, 1])

with col_cat:
    # Desplegable simple con las categorías que pides
    categoria = st.selectbox(
        "Categoría:",
        [
            "🍕 Comida / Supermercado",
            "🛍️ Caprichos",
            "👕 Ropa",
            "💡 Luz",
            "🔥 Gas",
            "🌐 Internet / Móvil",
            "📈 Inversión ING (ETF)",
            "💼 Nómina / Ingreso",
            "📦 Otros"
        ]
    )

with col_monto:
    monto = st.number_input("Importe (€):", min_value=0.0, step=5.0, value=10.0)

# Botón grande de guardar
if st.button("➕ Guardar Gasto", use_container_width=True):
    tipo = "Ingreso" if "Nómina" in categoria else "Gasto"
    st.session_state.transacciones.append({
        "Categoría": categoria,
        "Importe (€)": monto,
        "Tipo": tipo
    })
    st.success(f"¡Guardado! {categoria} por {monto:.2f} €")

# --- TABLA Y RESUMEN VISUAL ---
st.divider()
st.subheader("📊 Resumen")

if st.session_state.transacciones:
    df = pd.DataFrame(st.session_state.transacciones)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.dataframe(df, use_container_width=True)
        
    with col2:
        gastos = df[df["Tipo"] == "Gasto"]["Importe (€)"].sum()
        ingresos = df[df["Tipo"] == "Ingreso"]["Importe (€)"].sum()
        
        st.metric("Total Gastado", f"{gastos:.2f} €")
        st.metric("Total Ingresado", f"{ingresos:.2f} €")
        st.metric("Balance", f"{(ingresos - gastos):.2f} €")
else:
    st.info("Haz clic en 'Guardar Gasto' para empezar a acumular datos.")
