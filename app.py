import streamlit as st
import pandas as pd
import numpy as np

# Configuración de la página
st.set_page_config(page_title="Copiloto Financiero & Inversión", page_icon="💰", layout="wide")

st.title("💰 Copiloto Financiero & Proyección de Inversiones")

# Inicializar historial de transacciones en la sesión
if "transacciones" not in st.session_state:
    st.session_state.transacciones = []

# --- PESTAÑAS PRINCIPALES ---
tab1, tab2, tab3 = st.tabs(["⚡ Registro Gastos/Ingresos", "📈 Inversión & ETFs ING", "🤖 Asesor IA"])

# ==========================================
# PESTAÑA 1: GASTOS E INGRESOS
# ==========================================
with tab1:
    st.subheader("⚡ Registrar Nuevo Movimiento")
    
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
                "💼 Nómina / Ingreso",
                "📦 Otros"
            ]
        )
        
        detalle_otros = ""
        if categoria == "📦 Otros":
            detalle_otros = st.text_input("Especifica el concepto para 'Otros':", placeholder="Ej. Taller, seguro, regalo...")
            
    with col_monto:
        monto = st.number_input("Importe (€):", min_value=0.01, step=5.0, value=50.0)

    if st.button("➕ Guardar Movimiento", use_container_width=True):
        concepto_final = f"📦 Otros ({detalle_otros.strip()})" if (categoria == "📦 Otros" and detalle_otros.strip()) else categoria
        tipo = "Ingreso" if "Nómina" in categoria else "Gasto"
        
        st.session_state.transacciones.append({
            "Categoría / Concepto": concepto_final,
            "Importe (€)": monto,
            "Tipo": tipo
        })
        st.success(f"Registrado: {concepto_final} ({monto:.2f} €)")

    st.divider()
    st.subheader("📊 Balance de Movimientos")
    
    if st.session_state.transacciones:
        df = pd.DataFrame(st.session_state.transacciones)
        
        col_tabla, col_metrics = st.columns([2, 1])
        
        with col_tabla:
            st.dataframe(df, use_container_width=True)
            
        with col_metrics:
            total_ingresos = df[df["Tipo"] == "Ingreso"]["Importe (€)"].sum()
            total_gastos = df[df["Tipo"] == "Gasto"]["Importe (€)"].sum()
            balance = total_ingresos - total_gastos
            
            st.metric("Total Ingresos", f"{total_ingresos:.2f} €")
            st.metric("Total Gastos", f"{total_gastos:.2f} €")
            st.metric("Ahorro / Balance Libre", f"{balance:.2f} €")
    else:
        st.info("No hay movimientos registrados todavía. Utiliza el formulario superior.")

# ==========================================
# PESTAÑA 2: PROYECCIÓN DE INVERSIÓN (ETFs)
# ==========================================
with tab2:
    st.subheader("📈 Simulador de Interés Compuesto y Optimización ING")
    
    col_inputs, col_info = st.columns([1, 2])
    
    with col_inputs:
        st.markdown("#### Configuración del Plan")
        aporte_mensual = st.number_input("Ahorro mensual dedicado a ETF (€):", min_value=10.0, value=60.0, step=10.0)
        frecuencia_meses = st.slider("Frecuencia de compra en ING (Meses):", 1, 6, 4)
        rentabilidad_anual = st.slider("Rentabilidad anual estimada (%):", 1.0, 15.0, 7.0, step=0.5)
        anios = st.slider("Plazo de inversión (Años):", 1, 30, 10)
        
        comision_fija = 3.10
        capital_orden = aporte_mensual * frecuencia_meses
        impacto_com = (comision_fija / capital_orden) * 100
        
        st.markdown("---")
        st.markdown(f"**Orden en ING:** Cada {frecuencia_meses} meses ({capital_orden:.2f} €/compra)")
        st.markdown(f"**Impacto comisión fija (~3,10 €):** `{impacto_com:.2f}%`")
        
        if impacto_com <= 1.5:
            st.success("✅ Frecuencia eficiente para el Bróker ING.")
        else:
            st.warning("⚠️ Comisión alta en %. Te conviene acumular un mes más.")

    with col_info:
        st.markdown("#### Proyección de Crecimiento del Patrimonio")
        
        # Cálculo de la curva de interés compuesto mes a mes
        meses_totales = anios * 12
        r_mensual = (1 + rentabilidad_anual / 100) ** (1 / 12) - 1
        
        meses = list(range(1, meses_totales + 1))
        capital_aportado = []
        valor_portafolio = []
        
        acumulado_aportes = 0
        saldo_cuenta = 0
        
        for m in meses:
            acumulado_aportes += aporte_mensual
            # Aplicar rentabilidad al saldo invertido
            saldo_cuenta = (saldo_cuenta + aporte_mensual) * (1 + r_mensual)
            
            capital_aportado.append(acumulado_aportes)
            valor_portafolio.append(saldo_cuenta)
            
        df_proyeccion = pd.DataFrame({
            "Mes": meses,
            "Capital Aportado (€)": capital_aportado,
            "Valor Estimado (€)": valor_portafolio
        }).set_index("Mes")
        
        # Gráfico interactivo integrado
        st.line_chart(df_proyeccion)
        
        total_invertido = capital_aportado[-1]
        total_final = valor_portafolio[-1]
        ganancia_bruta = total_final - total_invertido
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Aportado", f"{total_invertido:,.2f} €")
        m2.metric("Valor Final Estimado", f"{total_final:,.2f} €")
        m3.metric("Beneficio Generado", f"+{ganancia_bruta:,.2f} €")

# ==========================================
# PESTAÑA 3: ASESOR CON IA (GEMINI)
# ==========================================
with tab3:
    st.subheader("🤖 Consultas con tu Copiloto Financiero")
    
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    pregunta = st.text_area("Plantea una duda sobre tu patrimonio, tus ETFs o tu estrategia:")
    
    if st.button("Consultar IA") and pregunta:
        if not api_key:
            st.error("Por favor, asegúrate de tener configurada la API Key en Secrets.")
        else:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                
                contexto = f"""
                Actúa como un copiloto financiero personal.
                Datos del usuario:
                - Ahorro mensual para ETFs: {aporte_mensual} €
                - Estrategia actual: Compra cada {frecuencia_meses} meses ({capital_orden} €/orden) en ING.
                - Rentabilidad esperada: {rentabilidad_anual}%
                - Plazo horizonte: {anios} años
                
                Duda del usuario: {pregunta}
                Responde de forma clara, directa y adaptada a su estrategia de inversión.
                """
                
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contexto
                )
                st.info(response.text)
            except Exception as e:
                st.error(f"Error al conectar con la IA: {e}")
