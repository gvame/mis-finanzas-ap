import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import json
import plotly.express as px
from supabase import create_client, Client

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Copiloto Financiero SaaS", page_icon="💰", layout="wide")

# --- CONTROL DE ACCESO PRIVADO ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔒 Acceso Privado")
    st.caption("Introduce tu clave personal para acceder a tu panel financiero.")
    
    password_input = st.text_input("Contraseña de acceso:", type="password")
    
    if st.button("Entrar", type="primary", use_container_width=True):
        if password_input == st.secrets.get("APP_PASSWORD"):
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    st.stop()

# --- CONEXIÓN A SUPABASE ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Error al conectar con Supabase: {e}")
    st.stop()

# --- BARRA LATERAL / CERRAR SESIÓN ---
with st.sidebar:
    st.write("👤 **Sesión Activa**")
    if st.button("🔒 Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()
    st.divider()

# --- FUNCIONES DE BASE DE DATOS ---
def cargar_transacciones():
    try:
        res = supabase.table("transacciones").select("*").execute()
        return res.data or []
    except Exception as e:
        st.error(f"Error al cargar transacciones: {e}")
        return []

def cargar_balance_base():
    transacciones = cargar_transacciones()
    for t in reversed(transacciones):
        if t.get("concepto") == "SALDO_INICIAL":
            return float(t.get("monto", 0.0))
    return 0.0

def actualizar_balance_base(nuevo_monto):
    try:
        supabase.table("transacciones").delete().eq("concepto", "SALDO_INICIAL").execute()
        supabase.table("transacciones").insert({
            "concepto": "SALDO_INICIAL",
            "monto": float(nuevo_monto),
            "tipo": "Config"
        }).execute()
        st.success("¡Capital inicial actualizado correctamente en la base de datos!")
    except Exception as e:
        st.error(f"Error detallado al actualizar saldo base: {e}")

def cargar_activos():
    try:
        res = supabase.table("activos").select("*").execute()
        return res.data or []
    except Exception as e:
        # Si la tabla no tuviera las columnas nuevas de tipo, no rompe la app
        return []

def registrar_movimiento_db(concepto, monto, tipo):
    try:
        supabase.table("transacciones").insert({
            "concepto": concepto,
            "monto": float(monto),
            "tipo": tipo
        }).execute()
    except Exception as e:
        st.error(f"Error al registrar movimiento: {e}")

def agregar_activo_db(ticker, nombre, acciones, precio_compra, tipo_activo="Acción/ETF"):
    try:
        supabase.table("activos").insert({
            "ticker": ticker,
            "nombre": nombre,
            "acciones": float(acciones),
            "precio_compra": float(precio_compra),
            "tipo_activo": tipo_activo
        }).execute()
    except Exception as e:
        # Fallback por si la columna tipo_activo aún no existe en Supabase
        try:
            supabase.table("activos").insert({
                "ticker": ticker,
                "nombre": nombre,
                "acciones": float(acciones),
                "precio_compra": float(precio_compra)
            }).execute()
        except Exception as err:
            st.error(f"Error al agregar activo: {err}")

# --- MERCADO Y COTIZACIONES EN TIEMPO REAL ---
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
            for q in res.get('quotes', []) if q.get('quoteType') in ['EQUITY', 'ETF', 'MUTUALFUND']
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

# --- CARGA INICIAL DE DATOS ---
transacciones = cargar_transacciones()
balance_base = cargar_balance_base()
activos = cargar_activos()

# --- CÁLCULOS MÉTRICOS PRINCIPALES ---
total_ingresos = sum(t.get("monto", 0) for t in transacciones if t.get("tipo") == "Ingreso")
total_gastos = sum(t.get("monto", 0) for t in transacciones if t.get("tipo") == "Gasto")
efectivo_disponible = balance_base + total_ingresos - total_gastos

valor_portafolio_actual = 0.0
total_invertido = 0.0

for a in activos:
    acciones = float(a.get("acciones", 0))
    p_compra = float(a.get("precio_compra", 0))
    tipo_act = a.get("tipo_activo", "Acción/ETF")
    
    inv = acciones * p_compra
    
    if tipo_act == "Depósito":
        # Para depósitos, el valor actual es el capital aportado (o con un interés estimado si se desea)
        p_actual = p_compra
    elif tipo_act == "Fondo Indexado":
        # Si tiene ticker de fondo indexado se intenta buscar, si no, se queda con el valor de compra o NAV ingresado
        ticker = a.get("ticker", "")
        p_actual = obtener_precio_eur(ticker) if ticker and ticker != "DEPOSITO" else p_compra
    else:
        # Acción / ETF normal
        p_actual = obtener_precio_eur(a.get("ticker", "")) or p_compra
        
    val = acciones * p_actual
    total_invertido += inv
    valor_portafolio_actual += val

capital_total = efectivo_disponible + valor_portafolio_actual

# --- INTERFAZ / PANEL SUPERIOR ---
st.title("💰 Copiloto Financiero & Portafolio")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Capital Total", f"{capital_total:,.2f} €")
m2.metric("Efectivo Libre", f"{efectivo_disponible:,.2f} €")
m3.metric("Valor Inversiones", f"{valor_portafolio_actual:,.2f} €")
ganancia_portafolio = valor_portafolio_actual - total_invertido
m4.metric("Rendimiento Inversiones", f"{ganancia_portafolio:+,.2f} €")

st.divider()

# --- PESTAÑAS DE NAVEGACIÓN ---
tab_cuenta, tab_gastos, tab_inversiones, tab_ia = st.tabs([
    "🏦 Cuenta Base", "⚡ Gastos e Ingresos", "📈 Inversiones", "🤖 Asesor IA Ejecutor"
])

# ==========================================
# 1. CUENTA BASE (EFECTIVO INICIAL)
# ==========================================
with tab_cuenta:
    st.subheader("⚙️ Configuración del Capital Inicial")
    st.caption("Introduce el saldo de partida en tu cuenta bancaria para fijar el efectivo base.")
    
    col_bal1, col_bal2 = st.columns([2, 1])
    with col_bal1:
        nuevo_balance = st.number_input("Capital Inicial de la Cuenta (€):", value=balance_base, min_value=0.0, step=100.0)
    with col_bal2:
        st.write("")
        st.write("")
        if st.button("Actualizar Capital Inicial", use_container_width=True):
            actualizar_balance_base(nuevo_balance)
            st.rerun()

# ==========================================
# 2. GASTOS E INGRESOS
# ==========================================
with tab_gastos:
    st.subheader("⚡ Registrar Nuevo Movimiento")
    col1, col2 = st.columns([2, 1])
    with col1:
        cat = st.selectbox("Categoría:", ["🍕 Comida", "🛍️ Caprichos", "👕 Ropa", "💡 Luz", "🔥 Gas", "🌐 Internet", "💼 Nómina", "📦 Otros"])
        det = st.text_input("Detalle (si es 'Otros'):") if cat == "📦 Otros" else ""
    with col2:
        monto = st.number_input("Importe (€):", min_value=0.01, value=50.0)
        
    if st.button("➕ Guardar Movimiento", use_container_width=True):
        concepto = f"📦 Otros ({det})" if det else cat
        tipo = "Ingreso" if "Nómina" in cat else "Gasto"
        registrar_movimiento_db(concepto, monto, tipo)
        st.success(f"Guardado: {concepto}")
        st.rerun()

    st.divider()
    st.subheader("📊 Historial de Transacciones")
    transacciones_visibles = [t for t in transacciones if t.get("tipo") != "Config"]
    if transacciones_visibles:
        df_trans = pd.DataFrame(transacciones_visibles)
        columnas_mostrar = [c for c in ["id", "created_at", "concepto", "monto", "tipo"] if c in df_trans.columns]
        st.dataframe(df_trans[columnas_mostrar], use_container_width=True)
    else:
        st.info("No hay gastos ni ingresos registrados.")

# ==========================================
# 3. INVERSIONES (Acciones, Fondos y Depósitos)
# ==========================================
with tab_inversiones:
    st.subheader("🏢 Gestión de Inversiones")
    
    tipo_seleccionado = st.radio("Selecciona el tipo de activo a añadir:", ["Acción / ETF", "Fondo Indexado", "Depósito Bancario"], horizontal=True)
    st.divider()
    
    if tipo_seleccionado == "Acción / ETF":
        busqueda = st.text_input("Buscar Acción o ETF (ej: Apple, Microsoft, S&P 500):", value="Apple")
        if busqueda:
            opciones = buscar_coincidencias(busqueda)
            if opciones:
                dict_opciones = {f"{item['name']} ({item['symbol']}) - {item['exchange']}": item for item in opciones}
                seleccion = st.selectbox("Selecciona activo verificado:", list(dict_opciones.keys()))
                activo_elegido = dict_opciones[seleccion]
                
                c_acc, c_prec = st.columns(2)
                with c_acc:
                    num_acc = st.number_input("Nº Acciones / Participaciones:", min_value=0.001, value=1.0)
                with c_prec:
                    prec_c = st.number_input("Precio compra medio (€):", min_value=0.0, value=150.0)
                    
                if st.button("Añadir Acción/ETF", use_container_width=True):
                    agregar_activo_db(activo_elegido["symbol"], activo_elegido["name"], num_acc, prec_c, "Acción/ETF")
                    st.success(f"Añadido {activo_elegido['name']} correctamente.")
                    st.rerun()

    elif tipo_seleccionado == "Fondo Indexado":
        st.caption("Añade tu fondo indexado (puedes buscar su ISIN/Ticker en Yahoo Finance o introducirlo manualmente).")
        f_nombre = st.text_input("Nombre del Fondo (ej: Vanguard Global Stock Index):", value="Vanguard Global Stock")
        f_ticker = st.text_input("Ticker / ISIN en Yahoo Finance (opcional, ej: 0P00001GMI.F o déjalo manual):", value="")
        
        c_part, c_vl = st.columns(2)
        with c_part:
            num_part = st.number_input("Número de Participaciones:", min_value=0.001, value=10.0)
        with c_vl:
            val_liq = st.number_input("Valor Liquidativo / Coste Medio (€):", min_value=0.0, value=100.0)
            
        if st.button("Añadir Fondo Indexado", use_container_width=True):
            ticker_val = f_ticker.strip() if f_ticker.strip() else "FONDO_MANUAL"
            agregar_activo_db(ticker_val, f_nombre, num_part, val_liq, "Fondo Indexado")
            st.success(f"Añadido fondo {f_nombre} correctamente.")
            st.rerun()

    else:
        st.caption("Registra tus depósitos a plazo fijo o cuentas remuneradas.")
        d_nombre = st.text_input("Nombre del Depósito (ej: Depósito Wizink 12M):", value="Depósito Plazo Fijo")
        d_capital = st.number_input("Capital Invertido (€):", min_value=0.0, value=5000.0)
        d_interes = st.number_input("Interés Anual Estimado (% TAE):", min_value=0.0, value=3.0)
        
        if st.button("Añadir Depósito", use_container_width=True):
            # Guardamos el capital como 'acciones' y el tipo de interés como 'precio_compra' o referencia
            agregar_activo_db("DEPOSITO", f"{d_nombre} ({d_interes}% TAE)", d_capital, 1.0, "Depósito")
            st.success(f"Añadido depósito {d_nombre} correctamente.")
            st.rerun()

    st.divider()
    st.subheader("💼 Desglose de Inversiones Actuales")

    if activos:
        tabla = []
        grafico_data = []
        grafico_tipo_data = {"Acción/ETF": 0.0, "Fondo Indexado": 0.0, "Depósito": 0.0}
        
        for item in activos:
            p_compra = float(item.get("precio_compra", 0))
            acciones = float(item.get("acciones", 0))
            ticker = item.get("ticker", "")
            nombre = item.get("nombre", ticker)
            tipo_act = item.get("tipo_activo", "Acción/ETF")
            
            if tipo_act == "Depósito":
                p_actual = 1.0
                inv = acciones * p_compra # Aquí 'acciones' guarda el capital total introducido
                val = inv
            elif tipo_act == "Fondo Indexado":
                p_actual = obtener_precio_eur(ticker) if ticker and ticker != "FONDO_MANUAL" else p_compra
                inv = acciones * p_compra
                val = acciones * p_actual
            else:
                p_actual = obtener_precio_eur(ticker) or p_compra
                inv = acciones * p_compra
                val = acciones * p_actual
                
            gan = val - inv
            pnl = (gan / inv) * 100 if inv > 0 else 0
            
            tabla.append({
                "Tipo": tipo_act,
                "Activo": nombre,
                "Cantidad / Título": acciones,
                "Precio/Coste (€)": f"{p_compra:.2f}",
                "Valor Actual (€)": f"{val:.2f}",
                "Rendimiento": f"{gan:+.2f} € ({pnl:+.2f}%)"
            })
            
            grafico_data.append({"Activo": nombre, "Valor (€)": val})
            if tipo_act in grafico_tipo_data:
                grafico_tipo_data[tipo_act] += val
            else:
                grafico_tipo_data["Acción/ETF"] += val
            
        st.dataframe(pd.DataFrame(tabla), use_container_width=True)
        
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("**Distribución por Tipo de Inversión**")
            df_tipos = pd.DataFrame([{"Tipo": k, "Valor": v} for k, v in grafico_tipo_data.items() if v > 0])
            if not df_tipos.empty:
                fig_pie_tipo = px.pie(df_tipos, names="Tipo", values="Valor", hole=0.4)
                st.plotly_chart(fig_pie_tipo, use_container_width=True)
            else:
                st.info("Sin datos para gráficos.")
            
        with col_g2:
            st.markdown("**Patrimonio: Efectivo vs Inversiones**")
            df_patrimonio = pd.DataFrame([
                {"Tipo": "Efectivo Libre", "Monto": efectivo_disponible},
                {"Tipo": "Inversiones", "Monto": valor_portafolio_actual}
            ])
            fig_bar = px.bar(df_patrimonio, x="Tipo", y="Monto", color="Tipo", text_auto=".2f")
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Añade tus inversiones (acciones, fondos o depósitos) para visualizar el desglose y gráficos.")

# ==========================================
# 4. ASESOR IA EJECUTOR
# ==========================================
with tab_ia:
    st.subheader("🤖 Pídele a la IA que gestione tu app")
    st.caption("Ejemplos: 'Apunta un gasto de 40 euros en supermercado' o 'Establece mi capital inicial en 3000 euros'.")
    
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    instruccion = st.text_area("Instrucción para la IA:")
    
    if st.button("Ejecutar Instrucción", use_container_width=True) and instruccion:
        if not api_key:
            st.error("Configura tu GEMINI_API_KEY en Secrets.")
        else:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                
                prompt_ia = f"""
                Eres el motor ejecutor de una app financiera.
                Analiza la petición del usuario: '{instruccion}'.
                
                Responde ÚNICAMENTE con un objeto JSON sin formato extra según el caso:
                1. Registro de gasto/ingreso:
                {{"accion": "movimiento", "concepto": "concepto", "monto": numero, "tipo": "Gasto" or "Ingreso"}}
                
                2. Cambiar capital inicial:
                {{"accion": "saldo_base", "monto": numero}}
                
                3. Consulta normal:
                {{"accion": "consulta", "respuesta": "texto de respuesta"}}
                """
                
                res = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt_ia
                )
                
                texto_limpio = res.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(texto_limpio)
                
                if data.get("accion") == "movimiento":
                    registrar_movimiento_db(data["concepto"], data["monto"], data["tipo"])
                    st.success(f"IA: Registrado {data['tipo']} de {data['monto']} € en '{data['concepto']}'.")
                elif data.get("accion") == "saldo_base":
                    actualizar_balance_base(data["monto"])
                    st.success(f"IA: Capital inicial actualizado a {data['monto']} €.")
                else:
                    st.info(data.get("respuesta", ""))
                    
                st.rerun()
            except Exception as e:
                st.error(f"Error de ejecución IA: {e}")
