import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import json

st.set_page_config(page_title="Copiloto Financiero SaaS", page_icon="💰", layout="wide")
st.title("💰 Copiloto Financiero Inteligente")

# --- CONTROL DE ESTADO (MEMORIA LOCAL / FUTURO SUPABASE) ---
if "transacciones" not in st.session_state:
    st.session_state.transacciones = []

if "mis_activos" not in st.session_state:
    st.session_state.mis_activos = []

# --- FUNCIONES DE SOPORTE Y MERCADO ---
def buscar_coincidencias(query):
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=5&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=5).json()
        return [
            {
                "symbol": q.get('symbol'),
                "name": q.get('longname') or q.get('shortname') or q.get('symbol'),
                "exchange": q.get('exchDisp') or q.get('exchange')
            }
            for q in res.get('quotes', []) if q.get('quoteType') in ['EQUITY', 'ETF']
        ]
    except Exception:
        return []

def obtener_precio_eur(ticker_code):
    try:
        stock = yf.Ticker(ticker_code)
        hist = stock.history(period="1d")
        if hist.empty:
            return None
        precio = float(hist['Close'].iloc[-1])
        currency = stock.fast_info.currency
        if currency == "USD":
            fx = yf.Ticker("EURUSD=X").history(period="1d")
            if not fx.empty:
                precio /= float(fx['Close'].iloc[-1])
        return precio
    except Exception:
        return None

# --- FUNCIONES EJECUTABLES POR LA IA ---
def registrar_movimiento_ia(concepto, monto, tipo):
    st.session_state.transacciones.append({
        "Concepto": concepto,
        "Importe (€)": float(monto),
        "Tipo": tipo
    })
    return f"Éxito: Se registró el {tipo} '{concepto}' por {monto} €."

def agregar_activo_ia(nombre_empresa, acciones, precio_compra):
    coincidencias = buscar_coincidencias(nombre_empresa)
    if coincidencias:
        elegido = coincidencias[0]
        st.session_state.mis_activos.append({
            "Ticker": elegido["symbol"],
            "Nombre": elegido["name"],
            "Acciones": float(acciones),
            "Precio_Compra": float(precio_compra)
        })
        return f"Éxito: Se añadió {elegido['name']} ({elegido['symbol']}) al portafolio."
    return f"Error: No se encontró la empresa '{nombre_empresa}'."

# --- PESTAÑAS DE LA APLICACIÓN ---
tab1, tab2, tab3 = st.tabs(["⚡ Gastos / Ingresos", "📈 Portafolio en Tiempo Real", "🤖 Copiloto IA Ejecutor"])

with tab1:
    st.subheader("⚡ Registrar Movimiento Manual")
    col1, col2 = st.columns([2, 1])
    with col1:
        cat = st.selectbox("Categoría:", ["🍕 Comida", "🛍️ Caprichos", "👕 Ropa", "💡 Luz", "🔥 Gas", "🌐 Internet", "💼 Nómina", "📦 Otros"])
        det = st.text_input("Detalle (si es 'Otros'):") if cat == "📦 Otros" else ""
    with col2:
        monto = st.number_input("Importe (€):", min_value=0.01, value=50.0)
        
    if st.button("➕ Guardar Movimiento", use_container_width=True):
        concepto = f"📦 Otros ({det})" if det else cat
        tipo = "Ingreso" if "Nómina" in cat else "Gasto"
        registrar_movimiento_ia(concepto, monto, tipo)
        st.success(f"Guardado: {concepto}")

    if st.session_state.transacciones:
        st.dataframe(pd.DataFrame(st.session_state.transacciones), use_container_width=True)

with tab2:
    st.subheader("🏢 Buscador de Activos Verificados")
    busqueda = st.text_input("Buscar empresa:", value="AeroVironment")
    
    if busqueda:
        opciones = buscar_coincidencias(busqueda)
        if opciones:
            dict_opciones = {f"{item['name']} ({item['symbol']}) - {item['exchange']}": item for item in opciones}
            seleccion = st.selectbox("Selecciona la empresa:", list(dict_opciones.keys()))
            activo_elegido = dict_opciones[seleccion]
            
            c_acc, c_prec = st.columns(2)
            with c_acc:
                num_acc = st.number_input("Nº Acciones:", min_value=0.001, value=1.0)
            with c_prec:
                prec_c = st.number_input("Precio compra medio (€):", min_value=0.0, value=150.0)
                
            if st.button("Añadir al Portafolio", use_container_width=True):
                st.session_state.mis_activos.append({
                    "Ticker": activo_elegido["symbol"],
                    "Nombre": activo_elegido["name"],
                    "Acciones": num_acc,
                    "Precio_Compra": prec_c
                })
                st.success(f"Añadido {activo_elegido['name']}.")

    st.divider()
    if st.session_state.mis_activos:
        tabla = []
        for item in st.session_state.mis_activos:
            p_actual = obtener_precio_eur(item["Ticker"]) or item["Precio_Compra"]
            inv = item["Acciones"] * item["Precio_Compra"]
            val = item["Acciones"] * p_actual
            gan = val - inv
            pnl = (gan / inv) * 100 if inv > 0 else 0
            
            tabla.append({
                "Ticker": item["Ticker"],
                "Empresa": item["Nombre"],
                "Acciones": item["Acciones"],
                "Precio Compra (€)": f"{item['Precio_Compra']:.2f}",
                "Precio Mercado (€)": f"{p_actual:.2f}",
                "Total Invertido (€)": f"{inv:.2f}",
                "Valor Actual (€)": f"{val:.2f}",
                "Rendimiento": f"{gan:+.2f} € ({pnl:+.2f}%)"
            })
        st.dataframe(pd.DataFrame(tabla), use_container_width=True)

with tab3:
    st.subheader("🤖 Pídele a la IA que gestione tu app")
    st.caption("Ejemplos: 'Apunta un gasto de 30 euros en luz' o 'Añade 2 acciones de Alphabet compradas a 140 euros'.")
    
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    instruccion = st.text_area("Instrucción para la IA:")
    
    if st.button("Ejecutar Instrucción") and instruccion:
        if not api_key:
            st.error("Configura tu API Key en Secrets.")
        else:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                
                # Prompt estructurado para interpretación de comandos
                prompt_ia = f"""
                Eres el motor de control de una app financiera.
                Analiza la petición del usuario: '{instruccion}'.
                
                Si quiere registrar un gasto o ingreso, responde ÚNICAMENTE en este formato JSON:
                {{"accion": "movimiento", "concepto": "nombre_concepto", "monto": numero, "tipo": "Gasto" o "Ingreso"}}
                
                Si quiere añadir un activo/empresa al portafolio, responde ÚNICAMENTE en este formato JSON:
                {{"accion": "activo", "empresa": "nombre_empresa", "acciones": numero, "precio_compra": numero}}
                
                Si es una consulta normal, responde con formato JSON:
                {{"accion": "consulta", "respuesta": "tu texto de respuesta"}}
                """
                
                res = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt_ia
                )
                
                # Parsear comando JSON enviado por Gemini
                texto_limpio = res.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(texto_limpio)
                
                if data.get("accion") == "movimiento":
                    msg = registrar_movimiento_ia(data["concepto"], data["monto"], data["tipo"])
                    st.success(msg)
                elif data.get("accion") == "activo":
                    msg = agregar_activo_ia(data["empresa"], data["acciones"], data["precio_compra"])
                    st.success(msg)
                else:
                    st.info(data.get("respuesta", "Instrucción procesada."))
                    
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo interpretar la orden. Detalle: {e}")
