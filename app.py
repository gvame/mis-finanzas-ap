import streamlit as st
import pandas as pd
from google import genai

# Configuración de la página
st.set_page_config(page_title="Mi Copiloto Financiero", page_icon="💰", layout="wide")

st.title("💰 Mi Copiloto Financiero & Inversión ING")

# --- BARRA LATERAL: DATOS FINANCIEROS ---
st.sidebar.header("Tus Datos Mensuales")
ingresos = st.sidebar.number_input("Ingresos mensuales (€)", value=600.0, step=50.0)
gastos = st.sidebar.number_input("Gastos fijos estimaciones (€)", value=480.0, step=10.0)
ahorro_objetivo = st.sidebar.number_input("Ahorro para ETF Emergentes ING (€)", value=60.0, step=10.0)

# --- PANEL PRINCIPAL ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Resumen del Mes")
    disponible = ingresos - gastos - ahorro_objetivo
    
    st.metric("Ingresos Totales", f"{ingresos:.2f} €")
    st.metric("Ahorro Reservado (ING)", f"{ahorro_objetivo:.2f} €")
    st.metric("Dinero Libre / Ocio", f"{disponible:.2f} €")

with col2:
    st.subheader("📈 Planificador ETF ING")
    meses_acumulo = st.slider("Meses acumulando ahorro", 1, 6, 4)
    total_acumulado = ahorro_objetivo * meses_acumulo
    comision_est = 3.10
    impacto_comision = (comision_est / total_acumulado) * 100 if total_acumulado > 0 else 0
    
    st.write(f"**Capital para tu próxima compra:** {total_acumulado:.2f} €")
    st.write(f"**Peso de la comisión de ING (~3,10 €):** {impacto_comision:.2f}%")
    
    if impacto_comision <= 1.5:
        st.success("¡Excelente eficiencia! Buen momento para ejecutar la orden en ING.")
    else:
        st.warning("Comisión algo alta en % sobre el total. Se recomienda acumular un mes más.")

# --- SECCIÓN DE IA CON GEMINI ---
st.divider()
st.subheader("🤖 Consulta a tu Asesor Financiero IA")

# Obtener API Key automáticamente desde Secrets o permitir entrada manual si no existe
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    api_key = st.text_input("Introduce tu API Key de Google AI Studio:", type="password")

pregunta = st.text_area("¿Qué duda financiera o de presupuesto tienes hoy?")

if st.button("Consultar IA") and pregunta:
    if not api_key:
        st.error("Por favor, guarda tu API Key en Secrets o introdúcela en el cuadro superior.")
    else:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
            Actúa como un asesor financiero personal accesible y prudente.
            Contexto del usuario:
            - Ingresos: {ingresos} €/mes
            - Gastos fijos: {gastos} €/mes
            - Ahorro para ETF Emergentes en ING: {ahorro_objetivo} €/mes
            - Disponibilidad libre: {disponible} €
            
            Pregunta del usuario: {pregunta}
            Responde de forma clara, concisa y adaptada a su presupuesto.
            """
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            st.info(response.text)
        except Exception as e:
            st.error(f"Error al conectar con la IA: {e}")
