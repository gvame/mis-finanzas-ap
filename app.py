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

# --- CONEXIÓN A SUPABASE (Forzando esquema público) ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    # Inicialización estándar y segura del cliente
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

# --- FUNCIONES DE BASE DE DATOS (Con manejo de errores seguro) ---
def cargar_transacciones():
    try:
        # Forzamos la cabecera y el esquema público de forma explícita si fuera necesario
        res = supabase.table("transacciones").select("*").execute()
        return res.data or []
    except Exception as e:
        # Si hay error de ruta, devolvemos lista vacía para no tumbar la app
        return []

def cargar_balance_base():
    try:
        transacciones = cargar_transacciones()
        for t in reversed(transacciones):
            if t.get("concepto") == "SALDO_INICIAL":
                return float(t.get("monto", 0.0))
    except Exception:
        pass
    return 0.0

def actualizar_balance_base(nuevo_monto):
    try:
        # Intentamos borrar el saldo inicial previo
        supabase.table("transacciones").delete().eq("concepto", "SALDO_INICIAL").execute()
    except Exception:
        pass
        
    try:
        # Insertamos el nuevo saldo inicial
        supabase.table("transacciones").insert({
            "concepto": "SALDO_INICIAL",
            "monto": float(nuevo_monto),
            "tipo": "Config"
        }).execute()
        st.success("Saldo base actualizado correctamente.")
    except Exception as e:
        st.error(f"Error al actualizar balance base en Supabase: {e}")

def cargar_activos():
    try:
        res = supabase.table("activos").select("*").execute()
        return res.data or []
    except Exception:
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

def agregar_activo_db(ticker, nombre, acciones, precio_compra):
    try:
        supabase.table("activos").insert({
            "ticker": ticker,
            "nombre": nombre,
            "acciones": float(acciones),
            "precio_compra": float(precio_compra)
        }).execute()
    except Exception as e:
        st.error(f"Error al agregar activo: {e}")

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
    inv = acciones * p_compra
    p_actual = obtener_precio_eur(a.get("ticker", "")) or p_compra
    val = acciones * p_actual
    total_invertido += inv
    valor_portafolio_actual += val

patrimonio_total = efectivo_disponible + valor_portafolio_actual

# --- INTERFAZ / PANEL SUPERIOR ---
st.title("💰 Copiloto Financiero & Portafolio")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Patrimonio Total", f"{patrimonio_total:,.2f} €")
m2.metric("Efectivo Libre", f"{efectivo_disponible:,.2f} €")
m3.metric("Valor Inversiones", f"{valor_portafolio_actual:,.2f} €")
ganancia_portafolio = valor_portafolio_actual - total_invertido
m4.metric("Rendimiento Inversiones", f"{ganancia_portafolio:+,.2f} €")

st.divider()

# --- PESTAÑAS DE NAVEGACIÓN ---
tab_cuenta, tab_gastos, tab_portafolio, tab_ia = st.tabs([
    "🏦 Cuenta Base", "⚡ Gastos e Ingresos", "📈 Portafolio & Gráficos", "🤖 Asesor IA Ejecutor"
])

# ==========================================
# 1. CUENTA BASE (EFECTIVO INICIAL)
# ==========================================
with tab_cuenta:
    st.subheader("⚙️ Configuración del Balance Base")
    st.caption("Introduce el saldo de partida en tu cuenta bancaria (sin incluir gastos/ingresos registrados ni inversiones).")
    
    col_bal1, col_bal2 = st.columns([2, 1])
    with col_bal1:
        nuevo_balance = st.number_input("Saldo Base de la Cuenta (€):", value=balance_base, min_value=0.0, step=100.0)
    with col_bal2:
        st.write("")
        st.write("")
        if st.button("Actualizar Saldo Base", use_container_width=True):
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
# 3. PORTAFOLIO & GRÁFICOS DINÁMICOS
# ==========================================
with tab_portafolio:
    st.subheader("🏢 Buscador y Agregador de Activos")
    busqueda = st.text_input("Buscar empresa/ETF (ej: AeroVironment, Alphabet, Apple):", value="AeroVironment")
    
    if busqueda:
        opciones = buscar_coincidencias(busqueda)
        if opciones:
            dict_opciones = {f"{item['name']} ({item['symbol']}) - {item['exchange']}": item for item in opciones}
            seleccion = st.selectbox("Selecciona activo verificado:", list(dict_opciones.keys()))
            activo_elegido = dict_opciones[seleccion]
            
            c_acc, c_prec = st.columns(2)
            with c_acc:
                num_acc = st.number_input("Nº Acciones:", min_value=0.001, value=1.0)
            with c_prec:
                prec_c = st.number_input("Precio compra medio (€):", min_value=0.0, value=150.0)
                
            if st.button("Añadir al Portafolio", use_container_width=True):
                agregar_activo_db(activo_elegido["symbol"], activo_elegido["name"], num_acc, prec_c)
                st.success(f"Añadido {activo_elegido['name']} a la base de datos.")
                st.rerun()

    st.divider()
    st.subheader("💼 Tu Portafolio Valorizado")

    if activos:
        tabla = []
        grafico_data = []
        
        for item in activos:
            p_compra = float(item.get("precio_compra", 0))
            acciones = float(item.get("acciones", 0))
            ticker = item.get("ticker", "")
            nombre = item.get("nombre", ticker)
            
            p_actual = obtener_precio_eur(ticker) or p_compra
            inv = acciones * p_compra
            val = acciones * p_actual
            gan = val - inv
            pnl = (gan / inv) * 100 if inv > 0 else 0
            
            tabla.append({
                "Ticker": ticker,
                "Empresa": nombre,
                "Acciones": acciones,
                "Precio Compra (€)": f"{p_compra:.2f}",
                "Precio Actual (€)": f"{p_actual:.2f}",
                "Invertido (€)": f"{inv:.2f}",
                "Valor Actual (€)": f"{val:.2f}",
                "Rendimiento": f"{gan:+.2f} € ({pnl:+.2f}%)"
            })
            grafico_data.append({"Empresa": nombre, "Valor (€)": val})
            
        st.dataframe(pd.DataFrame(tabla), use_container_width=True)
        
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("**Distribución de Inversiones**")
            fig_pie = px.pie(grafico_data, names="Empresa", values="Valor (€)", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_g2:
            st.markdown("**Patrimonio: Efectivo vs Inversiones**")
            df_patrimonio = pd.DataFrame([
                {"Tipo": "Efectivo Libre", "Monto": efectivo_disponible},
                {"Tipo": "Inversiones", "Monto": valor_portafolio_actual}
            ])
            fig_bar = px.bar(df_patrimonio, x="Tipo", y="Monto", color="Tipo", text_auto=".2f")
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Añade activos desde el buscador para visualizar gráficos en tiempo real.")

# ==========================================
# 4. ASESOR IA EJECUTOR
# ==========================================
with tab_ia:
    st.subheader("🤖 Pídele a la IA que gestione tu app")
    st.caption("Ejemplos: 'Apunta un gasto de 40 euros en supermercado', 'Añade 2 acciones de Apple a 180 euros' o 'Establece mi saldo base en 3000 euros'.")
    
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
                {{"accion": "movimiento", "concepto": "concepto", "monto": numero, "tipo": "Gasto" o "Ingreso"}}
                
                2. Añadir inversión:
                {{"accion": "activo", "empresa": "nombre_empresa", "acciones": numero, "precio_compra": numero}}
                
                3. Cambiar saldo base:
                {{"accion": "saldo_base", "monto": numero}}
                
                4. Consulta normal:
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
                elif data.get("accion") == "activo":
                    coincidencias = buscar_coincidencias(data["empresa"])
                    if coincidencias:
                        elegido = coincidencias[0]
                        agregar_activo_db(elegido["symbol"], elegido["name"], data["acciones"], data["precio_compra"])
                        st.success(f"IA: Añadido {elegido['name']} al portafolio.")
                    else:
                        st.error(f"IA: No se encontró la empresa {data['empresa']}.")
                elif data.get("accion") == "saldo_base":
                    actualizar_balance_base(data["monto"])
                    st.success(f"IA: Saldo base actualizado a {data['monto']} €.")
                else:
                    st.info(data.get("respuesta", ""))
                    
                st.rerun()
            except Exception as e:
                st.error(f"Error de ejecución IA: {e}")
