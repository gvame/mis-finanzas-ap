import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import json
import plotly.express as px
from datetime import date, datetime
from supabase import create_client, Client
import io

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

def agregar_activo_db(ticker, nombre, acciones, precio_compra, tipo_activo="Acción/ETF", fecha_inicio=None, fecha_fin=None, interes_tae=0.0):
    try:
        supabase.table("activos").insert({
            "ticker": ticker,
            "nombre": nombre,
            "acciones": float(acciones),
            "precio_compra": float(precio_compra),
            "tipo_activo": tipo_activo,
            "fecha_inicio": str(fecha_inicio) if fecha_inicio else None,
            "fecha_fin": str(fecha_fin) if fecha_fin else None,
            "interes_tae": float(interes_tae)
        }).execute()
    except Exception:
        try:
            supabase.table("activos").insert({
                "ticker": ticker,
                "nombre": nombre,
                "acciones": float(acciones),
                "precio_compra": float(precio_compra),
                "tipo_activo": tipo_activo
            }).execute()
        except Exception as err:
            st.error(f"Error al agregar activo: {err}")

# --- MERCADO Y COTIZACIONES EN TIEMPO REAL ---
def buscar_coincidencias(query):
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=6&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=5).json()
        return [
            {
                "symbol": q.get('symbol'),
                "name": q.get('longname') or q.get('shortname') or q.get('symbol'),
                "exchange": q.get('exchDisp') or q.get('exchange')
            }
            for q in res.get('quotes', []) if q.get('quoteType') in ['EQUITY', 'ETF', 'MUTUALFUND', 'INDEX']
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
        if currency and currency.upper() == "USD":
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
hoy = date.today()

for a in activos:
    acciones = float(a.get("acciones", 0))
    p_compra = float(a.get("precio_compra", 0))
    tipo_act = a.get("tipo_activo", "Acción/ETF")
    
    inv = acciones * p_compra
    
    if tipo_act == "Depósito":
        capital = acciones
        tae = float(a.get("interes_tae", 0.0)) / 100.0
        f_ini_str = a.get("fecha_inicio")
        f_fin_str = a.get("fecha_fin")
        
        ganancia_dep = 0.0
        if f_ini_str and f_fin_str:
            try:
                f_ini = datetime.strptime(str(f_ini_str).split()[0], "%Y-%m-%d").date()
                f_fin = datetime.strptime(str(f_fin_str).split()[0], "%Y-%m-%d").date()
                total_dias = (f_fin - f_ini).days
                dias_transcurridos = (hoy - f_ini).days
                dias_transcurridos = max(0, min(dias_transcurridos, total_dias))
                if total_dias > 0:
                    ganancia_dep = capital * (tae * (dias_transcurridos / 365.0))
            except Exception:
                pass
        val = capital + ganancia_dep
    elif tipo_act == "Fondo Indexado":
        ticker = a.get("ticker", "")
        p_actual = obtener_precio_eur(ticker) if ticker and ticker != "FONDO_MANUAL" else p_compra
        val = acciones * p_actual
    else:
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
# 3. INVERSIONES (Acciones, Fondos, Depósitos + Importación Masiva)
# ==========================================
with tab_inversiones:
    st.subheader("🏢 Gestión y Carga de Inversiones")
    
    opcion_carga = st.selectbox("Elige método de incorporación:", ["➕ Añadir Individualmente", "📁 Importación Masiva (Excel / CSV)"])
    st.divider()
    
    if opcion_carga == "📁 Importación Masiva (Excel / CSV)":
        st.markdown("### 📥 Sube tu cartera de golpe")
        st.caption("Sube un archivo Excel (.xlsx) o CSV con las columnas: `tipo_activo`, `ticker`, `nombre`, `acciones`, `precio_compra`")
        
        df_plantilla = pd.DataFrame([
            {"tipo_activo": "Acción/ETF", "ticker": "AAPL", "nombre": "Apple Inc.", "acciones": 10.0, "precio_compra": 150.0},
            {"tipo_activo": "Fondo Indexado", "ticker": "IE00B4L5Y983", "nombre": "Vanguard Global Stock", "acciones": 25.5, "precio_compra": 110.0},
            {"tipo_activo": "Depósito", "ticker": "DEPOSITO", "nombre": "Depósito Wizink", "acciones": 5000.0, "precio_compra": 1.0}
        ])
        
        buffer = io.BytesIO()
        df_plantilla.to_excel(buffer, index=False)
        buffer.seek(0)
        
        st.download_button(
            label="⬇️ Descargar Plantilla de Ejemplo (.xlsx)",
            data=buffer,
            file_name="plantilla_inversiones.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        archivo_subido = st.file_uploader("Sube tu archivo completado:", type=["xlsx", "csv"])
        if archivo_subido is not None:
            try:
                if archivo_subido.name.endswith('.csv'):
                    df_subida = pd.read_csv(archivo_subido)
                else:
                    df_subida = pd.read_excel(archivo_subido)
                
                if st.button("🚀 Procesar e Insertar Cartera en Supabase", type="primary"):
                    for _, row in df_subida.iterrows():
                        agregar_activo_db(
                            ticker=str(row.get("ticker", "MANUAL")),
                            nombre=str(row.get("nombre", "Activo")),
                            acciones=float(row.get("acciones", 0)),
                            precio_compra=float(row.get("precio_compra", 0)),
                            tipo_activo=str(row.get("tipo_activo", "Acción/ETF"))
                        )
                    st.success("¡Toda la cartera ha sido importada con éxito!")
                    st.rerun()
            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")

    else:
        tipo_seleccionado = st.radio("Tipo de activo:", ["Acción / ETF", "Fondo Indexado", "Depósito Bancario"], horizontal=True)
        st.write("")
        
        if tipo_seleccionado == "Acción / ETF":
            busqueda = st.text_input("Buscar Acción o ETF:", value="Apple")
            if busqueda:
                opciones = buscar_coincidencias(busqueda)
                if opciones:
                    dict_opciones = {f"{item['name']} ({item['symbol']}) - {item['exchange']}": item for item in opciones}
                    seleccion = st.selectbox("Selecciona activo:", list(dict_opciones.keys()))
                    activo_elegido = dict_opciones[seleccion]
                    
                    c_acc, c_prec = st.columns(2)
                    with c_acc:
                        num_acc = st.number_input("Nº Acciones:", min_value=0.001, value=1.0)
                    with c_prec:
                        prec_c = st.number_input("Precio compra medio (€):", min_value=0.0, value=150.0)
                        
                    if st.button("Añadir Acción/ETF", use_container_width=True):
                        agregar_activo_db(activo_elegido["symbol"], activo_elegido["name"], num_acc, prec_c, "Acción/ETF")
                        st.success("Añadido correctamente.")
                        st.rerun()

        elif tipo_seleccionado == "Fondo Indexado":
            f_busqueda = st.text_input("Buscar Fondo (nombre o ISIN):", value="Vanguard")
            f_ticker_final = "FONDO_MANUAL"
            f_nombre_final = f_busqueda
            
            if f_busqueda:
                opciones_fondo = buscar_coincidencias(f_busqueda)
                if opciones_fondo:
                    dict_f = {f"{item['name']} ({item['symbol']})": item for item in opciones_fondo}
                    sel_f = st.selectbox("Selecciona fondo:", list(dict_f.keys()))
                    f_ticker_final = dict_f[sel_f]["symbol"]
                    f_nombre_final = dict_f[sel_f]["name"]
                    
            c_part, c_vl = st.columns(2)
            with c_part:
                num_part = st.number_input("Nº Participaciones:", min_value=0.001, value=10.0)
            with c_vl:
                val_liq = st.number_input("Valor Liquidativo Medio (€):", min_value=0.0, value=100.0)
                
            if st.button("Añadir Fondo Indexado", use_container_width=True):
                agregar_activo_db(f_ticker_final, f_nombre_final, num_part, val_liq, "Fondo Indexado")
                st.success("Añadido fondo correctamente.")
                st.rerun()

        else:
            d_nombre = st.text_input("Nombre del Depósito:", value="Depósito Plazo Fijo")
            d_capital = st.number_input("Capital Invertido (€):", min_value=0.0, value=5000.0)
            d_interes = st.number_input("Interés Anual (% TAE):", min_value=0.0, value=3.0)
            c_d1, c_d2 = st.columns(2)
            with c_d1:
                f_inicio = st.date_input("Fecha Inicio:", value=date.today())
            with c_d2:
                f_fin = st.date_input("Fecha Vencimiento:", value=date(date.today().year + 1, date.today().month, date.today().day))
                
            if st.button("Añadir Depósito", use_container_width=True):
                agregar_activo_db("DEPOSITO", d_nombre, d_capital, 1.0, "Depósito", fecha_inicio=f_inicio, fecha_fin=f_fin, interes_tae=d_interes)
                st.success("Añadido depósito correctamente.")
                st.rerun()

    st.divider()
    
    c_inf1, c_inf2 = st.columns([3, 1])
    with c_inf1:
        st.subheader("💼 Desglose de Inversiones Actuales")
    with c_inf2:
        modo_rentabilidad = st.radio("Ver rentabilidad en:", ["%", "€"], horizontal=True, label_visibility="collapsed")

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
                capital = acciones
                tae = float(item.get("interes_tae", 0.0)) / 100.0
                f_ini_str = item.get("fecha_inicio")
                f_fin_str = item.get("fecha_fin")
                
                ganancia_dep = 0.0
                if f_ini_str and f_fin_str:
                    try:
                        f_ini = datetime.strptime(str(f_ini_str).split()[0], "%Y-%m-%d").date()
                        f_fin = datetime.strptime(str(f_fin_str).split()[0], "%Y-%m-%d").date()
                        total_dias = (f_fin - f_ini).days
                        dias_transcurridos = (hoy - f_ini).days
                        dias_transcurridos = max(0, min(dias_transcurridos, total_dias))
                        if total_dias > 0:
                            ganancia_dep = capital * (tae * (dias_transcurridos / 365.0))
                    except Exception:
                        pass
                inv = capital
                val = capital + ganancia_dep
                gan = ganancia_dep
                pnl = (gan / inv) * 100 if inv > 0 else 0
            elif tipo_act == "Fondo Indexado":
                p_actual = obtener_precio_eur(ticker) if ticker and ticker != "FONDO_MANUAL" else p_compra
                inv = acciones * p_compra
                val = acciones * p_actual
                gan = val - inv
                pnl = (gan / inv) * 100 if inv > 0 else 0
            else:
                p_actual = obtener_precio_eur(ticker) or p_compra
                inv = acciones * p_compra
                val = acciones * p_actual
                gan = val - inv
                pnl = (gan / inv) * 100 if inv > 0 else 0
                
            if modo_rentabilidad == "%":
                txt_rent = f"{pnl:+.2f}%"
            else:
                txt_rent = f"{gan:+.2f} €"
                
            color_estilo = "color: #2e7d32; font-weight: bold;" if gan >= 0 else "color: #c62828; font-weight: bold;"
            rentabilidad_html = f'<span style="{color_estilo}">{txt_rent}</span>'
            
            tabla.append({
                "Tipo": tipo_act,
                "Activo": nombre,
                "Invertido (€)": f"{inv:,.2f}",
                "Valor Actual (€)": f"{val:,.2f}",
                "Rentabilidad": rentabilidad_html
            })
            
            grafico_data.append({"Activo": nombre, "Valor (€)": val})
            if tipo_act in grafico_tipo_data:
                grafico_tipo_data[tipo_act] += val
            else:
                grafico_tipo_data["Acción/ETF"] += val
            
        df_tabla = pd.DataFrame(tabla)
        st.markdown(df_tabla.to_html(escape=False, index=False), unsafe_allow_html=True)
        
        st.write("")
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
            st.markdown("**Capital: Efectivo vs Inversiones**")
            df_patrimonio = pd.DataFrame([
                {"Tipo": "Efectivo Libre", "Monto": efectivo_disponible},
                {"Tipo": "Inversiones", "Monto": valor_portafolio_actual}
            ])
            fig_bar = px.bar(df_patrimonio, x="Tipo", y="Monto", color="Tipo", text_auto=".2f")
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Añade tus inversiones de forma manual, por IA o subiendo una plantilla Excel para empezar.")

# ==========================================
# 4. ASESOR IA EJECUTOR (DICTA TU CARTERA AQUÍ)
# ==========================================
with tab_ia:
    st.subheader("🤖 Asistente IA Dictador de Cartera")
    st.caption("Escribe en lenguaje natural lo que tienes invertido y la IA lo estructurará, buscará los tickers y lo guardará sola en tu base de datos.")
    
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    instruccion = st.text_area("Cuéntale a la IA tus movimientos o cartera:", placeholder="Ejemplo: Tengo 10 acciones de Apple a 150€, 20 participaciones de un fondo Vanguard S&P 500 a 100€, y un depósito de 4000€ al 2.5%...")
    
    if st.button("Ejecutar con IA", use_container_width=True) and instruccion:
        if not api_key:
            st.error("Configura tu GEMINI_API_KEY en Secrets.")
        else:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                
                prompt_ia = f"""
                Eres el motor ejecutor y experto financiero de una app. Analiza la petición del usuario: '{instruccion}'.
                El usuario puede querer registrar un gasto, un ingreso, cambiar el capital inicial, o añadir uno o varios activos de inversión.
                
                Debes interpretar la petición y responder ÚNICAMENTE con un JSON puro (sin bloques de código markdown extra tipo ```json) con esta estructura:
                
                Si es un movimiento de gasto/ingreso:
                {{"accion": "movimiento", "concepto": "...", "monto": 0.0, "tipo": "Gasto" or "Ingreso"}}
                
                Si es para cambiar el saldo base inicial:
                {{"accion": "saldo_base", "monto": 0.0}}
                
                Si es para añadir una o varias inversiones (puede ser una lista):
                {{
                  "accion": "inversion",
                  "items": [
                    {{
                      "tipo_activo": "Acción/ETF" o "Fondo Indexado" o "Depósito",
                      "ticker": "Ticker de Yahoo Finance si lo conoces (ej AAPL, MSFT) o busca uno lógico, si es depósito pon DEPOSITO",
                      "nombre": "Nombre descriptivo",
                      "acciones": numero_de_acciones_o_participaciones_o_capital_en_deposito,
                      "precio_compra": precio_medio_o_1_si_es_deposito,
                      "fecha_inicio": "YYYY-MM-DD o null si no aplica",
                      "fecha_fin": "YYYY-MM-DD o null si no aplica",
                      "interes_tae": 0.0
                    }}
                  ]
                }}
                
                Si es una simple pregunta o consulta general:
                {{"accion": "consulta", "respuesta": "texto de respuesta"}}
                """
                
                res = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt_ia
                )
                
                texto_limpio = res.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(texto_limpio)
                
                accion = data.get("accion")
                if accion == "movimiento":
                    registrar_movimiento_db(data["concepto"], data["monto"], data["tipo"])
                    st.success(f"IA: Registrado {data['tipo']} de {data['monto']} € en '{data['concepto']}'.")
                elif accion == "saldo_base":
                    actualizar_balance_base(data["monto"])
                    st.success(f"IA: Capital inicial actualizado a {data['monto']} €.")
                elif accion == "inversion":
                    items = data.get("items", [])
                    for it in items:
                        agregar_activo_db(
                            ticker=it.get("ticker", "MANUAL"),
                            nombre=it.get("nombre", "Activo"),
                            acciones=float(it.get("acciones", 0)),
                            precio_compra=float(it.get("precio_compra", 0)),
                            tipo_activo=it.get("tipo_activo", "Acción/ETF"),
                            fecha_inicio=it.get("fecha_inicio"),
                            fecha_fin=it.get("fecha_fin"),
                            interes_tae=float(it.get("interes_tae", 0.0))
                        )
                    st.success(f"¡IA: Se han añadido con éxito {len(items)} activos/inversiones a tu portafolio!")
                else:
                    st.info(data.get("respuesta", ""))
                    
                st.rerun()
            except Exception as e:
                st.error(f"Error procesando la instrucción con IA: {e}")
