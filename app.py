import streamlit as st
import pandas as pd

st.set_page_config(page_title="Mi Copiloto Financiero", page_icon="💰", layout="wide")
st.title("💰 Registro Rápido de Gastos")

if "transacciones" not in st.session_state:
    st.session_state.transacciones = []

# --- FORMULARIO RÁPIDO ---
st.subheader("⚡ Añadir nuevo movimiento")

col_cat, col_monto = st.columns([2, 1])

with col_cat:
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
    
    # Si selecciona "Otros", se despliega una casilla para escribir el detalle
    detalle_personalizado = ""
    if categoria == "📦 Otros":
        detalle_personalizado = st.text_input("Especifica el concepto para 'Otros':", placeholder="Ej. Reparación coche, regalo...")

with col_monto:
    monto = st.number_input("Importe (€):", min_value=0.0, step=5.0, value=10.0)

# Botón guardar
if st.button("➕ Guardar Gasto", use_container_width=True):
    # Definir la etiqueta final del concepto
    if categoria == "📦 Otros" and detalle_personalizado.strip() != "":
        categoria_final = f"📦 Otros ({detalle_personalizado.strip()})"
    else:
        categoria_final = categoria

    tipo = "Ingreso" if "Nómina" in categoria else "Gasto"
    
    st.session_state.transacciones.append({
        "Categoría": categoria_final,
        "Importe (€)": monto,
        "Tipo": tipo
    })
    st.success(f"¡Guardado! {categoria_final} por {monto:.2f} €")

# --- TABLA Y RESUMEN ---
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
