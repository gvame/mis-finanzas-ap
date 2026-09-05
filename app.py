import streamlit as st
import pandas as pd
import yfinance as yf
import requests

# Configuración de la página
st.set_page_config(page_title="Copiloto Financiero & Inversión", page_icon="💰", layout="wide")

st.title("💰 Copiloto Financiero & Portafolio Dinámico")

# Inicialización de estado en sesión
if "transacciones" not in st.session_state:
    st.session_state.transacciones = []

if "mis_activos" not in st.session_state:
    st.session_state.mis_activos = [
        {"Ticker": "GOOGL", "Nombre": "Alphabet Inc.", "Acciones": 2.0, "Precio_Compra": 150.0}
    ]

# Función para buscar el Ticker exacto a partir del nombre comercial
def buscar_ticker(nombre_busqueda):
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={nombre_busqueda}&quotesCount=5&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers)
        datos = response.json()
        quotes = datos.get('quotes', [])
        
        if quotes:
            for q in quotes:
                if q.get('quoteType') in ['EQUITY', 'ETF']:
                    return q.get('symbol'), q.get('longname', q.get('shortname', nombre_busqueda))
            return quotes[0].get('symbol'), quotes[0].get('shortname', nombre_busqueda)
    except Exception as e:
        st.error(f"Error al conectar con el servicio de búsqueda: {e}")
    
    return None, None

tab1, tab2, tab3 = st.tabs(["⚡ Registro Gastos/Ingresos", "📈 Portafolio & Empresas Dinámicas", "🤖 Asesor IA"])

# ==========================================
# PESTAÑA 1: GASTOS E INGRESOS
# ==========================================
with tab1:
    st.subheader("⚡ Registrar Nuevo Movimiento")
    col_cat, col_monto = st.columns([2, 1])
    
    with col_cat:
        categoria = st.selectbox(
            "Categoría:",
            ["🍕 Comida / Supermercado", "🛍️ Caprichos", "👕 Ropa", "💡 Luz", "🔥 Gas", "🌐 Internet / Móvil", "💼 Nómina / Ingreso", "📦 Otros"]
        )
        detalle_otros = ""
        if categoria == "📦 Otros":
            detalle_otros = st.text_input("Especifica el concepto para 'Otros':", placeholder="Ej. Taller, regalo...")
            
    with col_monto:
        monto = st.number_input("Importe (€):", min_value=0.01, step=5.0, value=50.0)

    if st.button("➕ Guardar Movimiento", use_container_width=True):
        concepto_final = f"📦 Otros ({detalle_otros.strip()})" if (categoria == "📦 Otros" and detalle_otros.strip()) else categoria
        tipo = "Ingreso" if "Nómina" in categoria else "Gasto"
        st.session_state.transacciones.append({"Categoría / Concepto": concepto_final, "Importe (€)": monto, "Tipo": tipo})
        st.success(f"Registrado: {concepto_final} ({monto:.2f} €)")

    st.divider()
    st.subheader("📊 Balance de Movimientos")
    if st.session_state.transacciones:
        df_trans = pd.DataFrame(st.session_state.transacciones)
        st.dataframe(df_trans, use_container_width=True)
    else:
        st.info("No hay movimientos registrados en esta sesión.")

# ==========================================
# PESTAÑA 2: PORTAFOLIO DINÁMICO & BOLSAS
# ==========================================
with tab2:
    st.subheader("🏢 Buscador y Agregador Inteligente de Empresas / ETFs")
    st.caption("Escribe el nombre de cualquier empresa (ej: AeroVironment, Alphabet, Apple) o su Ticker (ej: AVAV, GOOGL, AAPL).")

    # Formulario dinámico con búsqueda por nombre
    with st.expander("➕ Añadir nueva empresa o ETF al panel", expanded=True):
        col_busqueda, col_acciones, col_precio = st.columns([2, 1, 1])
        
        with col_busqueda:
            entrada_empresa = st.text_input("Nombre o Ticker de la empresa:", value="AeroVironment")
        with col_acciones:
            num_acciones = st.number_input("Nº de Acciones:", min_value=0.001, value=1.0, step=1.0)
        with col_precio:
            precio_compra = st.number_input("Precio medio compra ($/€):", min_value=0.0, value=100.0, step=10.0)
            
        if st.button("Buscar y Añadir al Portafolio", use_container_width=True) and entrada_empresa:
            ticker_encontrado, nombre_completo = buscar_ticker(entrada_empresa)
            
            if ticker_encontrado:
                st.session_state.mis_activos.append({
                    "Ticker": ticker_encontrado,
                    "Nombre": nombre_completo,
                    "Acciones": num_acciones,
                    "Precio_Compra": precio_compra
                })
                st.success(f"¡Añadido con éxito! **{nombre_completo}** (`{ticker_encontrado}`)")
            else:
                st.error("No se encontró ninguna empresa que coincida con esa búsqueda.")

    st.divider()
    st.subheader("💼 Tu Portafolio en Tiempo Real")

    if st.session_state.mis_activos:
        filas_portafolio = []
        
        for item in st.session_state.mis_activos:
            ticker_code = item["Ticker"]
            try:
                stock_data = yf.Ticker(ticker_code)
                precio_actual = stock_data.fast_info.last_price
            except:
                precio_actual = item["Precio_Compra"]
                
            inversion_inicial = item["Acciones"] * item["Precio_Compra"]
            valor_actual = item["Acciones"] * precio_actual
            ganancia = valor_actual - inversion_inicial
            pnl_pct = (ganancia / inversion_inicial) * 100 if inversion_inicial > 0 else 0
            
            filas_portafolio.append({
                "Ticker": ticker_code,
                "Empresa": item["Nombre"],
                "Acciones": item["Acciones"],
                "Precio Compra": f"{item['Precio_Compra']:.2f}",
                "Precio Actual": f"{precio_actual:.2f}",
                "Invertido": f"{inversion_inicial:.2f} €",
                "Valor Actual": f"{valor_actual:.2f} €",
                "Rendimiento": f"{ganancia:+.2f} € ({pnl_pct:+.2f}%)"
            })
            
        df_port = pd.DataFrame(filas_portafolio)
        st.dataframe(df_port, use_container_width=True)
    else:
        st.info("No has añadido ninguna empresa aún. Utiliza el buscador superior.")

    # --- COMPARATIVA DE COMISIONES BROKERS ---
    st.divider()
    st.subheader("⚖️ Comparador de Comisiones de Compra")
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.markdown("**ING (Bróker NARANJA)**")
        st.write("• **Bolsa / ETFs:** ~3,95 € - 8,00 € por orden nacional + cánones.")
        st.write("• **Bolsa Internacional (EE. UU.):** Comisiones fijas + 0,05 % cambio divisa.")
        st.write("• **Custodia:** 0 € si operas al menos 1 vez cada 3 meses.")
    
    with col_b2:
        st.markdown("**Trade Republic**")
        st.write("• **Bolsa / ETFs:** 1,00 € tarifa plana por orden manual.")
        st.write("• **Planes de Inversión:** 0,00 € (Automatizado).")
        st.write("• **Custodia:** 0 € sin condiciones.")

# ==========================================
# PESTAÑA 3: ASESOR IA
# ==========================================
with tab3:
    st.subheader("🤖 Consultas con tu Copiloto Financiero")
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    pregunta = st.text_area("Consulta a la IA sobre las empresas de tu portafolio o comisiones:")
    
    if st.button("Consultar IA") and pregunta:
        if not api_key:
            st.error("Configura tu API Key en Secrets.")
        else:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                
                contexto = f"""
                Actúa como copiloto financiero.
                Empresas en portafolio del usuario: {st.session_state.mis_activos}
                Pregunta: {pregunta}
                """
                response = client.models.generate_content(model="gemini-2.5-flash", contents=contexto)
                st.info(response.text)
            except Exception as e:
                st.error(f"Error: {e}")
