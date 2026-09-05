import streamlit as st
import pandas as pd
import yfinance as yf
import requests

st.set_page_config(page_title="Copiloto Financiero", page_icon="💰", layout="wide")
st.title("💰 Copiloto Financiero & Portafolio Dinámico")

if "transacciones" not in st.session_state:
    st.session_state.transacciones = []

if "mis_activos" not in st.session_state:
    st.session_state.mis_activos = []

# --- FUNCIONES DE BÚSQUEDA Y COTIZACIÓN VERÍDICA ---
def buscar_coincidencias(query):
    """Devuelve hasta 5 coincidencias exactas para que el usuario elija la correcta."""
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=5&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    resultados = []
    
    try:
        res = requests.get(url, headers=headers, timeout=5).json()
        for q in res.get('quotes', []):
            if q.get('quoteType') in ['EQUITY', 'ETF']:
                symbol = q.get('symbol')
                name = q.get('longname') or q.get('shortname') or symbol
                exch = q.get('exchDisp') or q.get('exchange')
                resultados.append({"symbol": symbol, "name": name, "exchange": exch})
    except Exception:
        pass
    return resultados

def obtener_precio_eur(ticker_code):
    """Obtiene la cotización en tiempo real y la convierte a EUR si cotiza en USD."""
    try:
        stock = yf.Ticker(ticker_code)
        hist = stock.history(period="1d")
        
        if hist.empty:
            return None
            
        precio = float(hist['Close'].iloc[-1])
        currency = stock.fast_info.currency
        
        # Conversión dinámica USD -> EUR
        if currency == "USD":
            fx = yf.Ticker("EURUSD=X").history(period="1d")
            if not fx.empty:
                rate = float(fx['Close'].iloc[-1])
                precio = precio / rate
                
        return precio
    except Exception:
        return None

# --- PESTAÑAS ---
tab1, tab2 = st.tabs(["⚡ Gastos / Ingresos", "📈 Portafolio en Tiempo Real"])

with tab1:
    st.subheader("⚡ Registrar Movimiento")
    col1, col2 = st.columns([2, 1])
    with col1:
        cat = st.selectbox("Categoría:", ["🍕 Comida", "🛍️ Caprichos", "👕 Ropa", "💡 Luz", "🔥 Gas", "🌐 Internet", "💼 Nómina", "📦 Otros"])
        det = st.text_input("Detalle (si es 'Otros'):") if cat == "📦 Otros" else ""
    with col2:
        monto = st.number_input("Importe (€):", min_value=0.01, value=50.0)
        
    if st.button("➕ Guardar Movimiento", use_container_width=True):
        concepto = f"📦 Otros ({det})" if det else cat
        tipo = "Ingreso" if "Nómina" in cat else "Gasto"
        st.session_state.transacciones.append({"Concepto": concepto, "Importe (€)": monto, "Tipo": tipo})
        st.success(f"Guardado: {concepto}")

    if st.session_state.transacciones:
        st.dataframe(pd.DataFrame(st.session_state.transacciones), use_container_width=True)

with tab2:
    st.subheader("🏢 Buscador de Activos Verificados")
    
    # 1. Búsqueda por texto
    busqueda = st.text_input("Escribe el nombre de la empresa (ej: AeroVironment, Alphabet, Apple):", value="AeroVironment")
    
    if busqueda:
        opciones = buscar_coincidencias(busqueda)
        if opciones:
            # Desplegable para seleccionar la empresa correcta y evitar errores
            dict_opciones = {f"{item['name']} ({item['symbol']}) - Mercado: {item['exchange']}": item for item in opciones}
            seleccion = st.selectbox("Selecciona la empresa correcta de la lista:", list(dict_opciones.keys()))
            
            activo_elegido = dict_opciones[seleccion]
            
            col_acc, col_prec = st.columns(2)
            with col_acc:
                num_acciones = st.number_input("Nº de Acciones:", min_value=0.001, value=1.0)
            with col_prec:
                precio_compra = st.number_input("Tu precio de compra medio (€):", min_value=0.0, value=150.0)
                
            if st.button("Añadir al Portafolio", use_container_width=True):
                st.session_state.mis_activos.append({
                    "Ticker": activo_elegido["symbol"],
                    "Nombre": activo_elegido["name"],
                    "Acciones": num_acciones,
                    "Precio_Compra": precio_compra
                })
                st.success(f"Añadido {activo_elegido['name']} al panel.")
        else:
            st.warning("No se encontraron coincidencias exactas.")

    st.divider()
    st.subheader("💼 Tu Portafolio Valorizado en Euros (€)")

    if st.session_state.mis_activos:
        tabla = []
        for item in st.session_state.mis_activos:
            precio_actual_eur = obtener_precio_eur(item["Ticker"])
            if precio_actual_eur is None:
                precio_actual_eur = item["Precio_Compra"]
                
            inv_inicial = item["Acciones"] * item["Precio_Compra"]
            val_actual = item["Acciones"] * precio_actual_eur
            ganancia = val_actual - inv_inicial
            pnl_pct = (ganancia / inv_inicial) * 100 if inv_inicial > 0 else 0
            
            tabla.append({
                "Ticker": item["Ticker"],
                "Empresa": item["Nombre"],
                "Acciones": item["Acciones"],
                "Precio Compra (€)": f"{item['Precio_Compra']:.2f}",
                "Precio Mercado (€)": f"{precio_actual_eur:.2f}",
                "Total Invertido (€)": f"{inv_inicial:.2f}",
                "Valor Actual (€)": f"{val_actual:.2f}",
                "Rendimiento": f"{ganancia:+.2f} € ({pnl_pct:+.2f}%)"
            })
            
        st.dataframe(pd.DataFrame(tabla), use_container_width=True)
    else:
        st.info("Añade un activo desde el buscador superior.")
