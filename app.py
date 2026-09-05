import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import json
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

def cargar_saldos_cuentas():
    try:
        res = supabase.table("transacciones").select("*").eq("tipo", "Config_Cuenta").execute()
        saldos = {"Cuenta Nómina": 0.0, "Cuenta Naranja": 0.0, "Trade Republic": 0.0}
        for t in res.data or []:
            concepto = t.get("concepto")
            for cuenta in saldos.keys():
                if cuenta in concepto:
                    saldos[cuenta] = float(t.get("monto", 0.0))
        return saldos
    except Exception:
        return {"Cuenta Nómina": 0.0, "Cuenta Naranja": 0.0, "Trade Republic": 0.0}

def actualizar_saldo_cuenta(nombre_cuenta, nuevo_monto):
    concepto_clave = f"SALDO_CUENTA_{nombre_cuenta}"
    try:
        supabase.table("transacciones").delete().eq("concepto", concepto_clave).execute()
        supabase.table("transacciones").insert({
            "concepto": concepto_clave,
            "monto": float(nuevo_monto),
            "tipo": "Config_Cuenta"
        }).execute()
        st.success(f"¡Saldo de '{nombre_cuenta}' actualizado correctamente!")
    except Exception as e:
        st.error(f"Error al actualizar saldo de {nombre_cuenta}: {e}")

def cargar_activos():
    try:
        res = supabase.table("activos").select("*").execute()
        return res.data or []
    except Exception:
        return []

def eliminar_activo_db(activo_id):
    try:
        supabase.table("activos").delete().eq("id", activo_id).execute()
        st.success("Activo eliminado correctamente.")
    except Exception as e:
        st.error(f"Error al eliminar activo: {e}")

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
                "precio_compra": float(precio_compra)
            }).execute()
        except Exception as err:
            st.error(f"Error crítico al agregar activo: {err}")

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
saldos_cuentas = cargar_saldos_cuentas()
activos = cargar_activos()

# --- CÁLCULOS MÉTRICOS PRINCIPALES ---
total_ingresos = sum(t.get("monto", 0) for t in transacciones if t.get("tipo") == "Ingreso")
total_gastos = sum(t.get("monto", 0) for t in transacciones if t.get("tipo") == "Gasto")

efectivo_base_total = sum(saldos_cuentas.values())
efectivo_disponible = efectivo_base_total + total_ingresos - total_gastos

valor_portafolio_actual = 0.0
total_invertido = 0.0
hoy = date.today()

for a in activos:
    acciones = float(a.get("acciones", 0))
    p_compra = float(a.get("precio_compra", 0))
    tipo_act = a.get("tipo_activo", "Acción/ETF")
    
    inv = acciones * p_compra
    
    if tipo_act in ["Depósito", "Cuenta Remunerada"]:
        capital = acciones
        tae = float(a.get("interes_tae", 0.0)) / 100.0
        f_ini_str = a.get("fecha_inicio")
        
        ganancia_dep = 0.0
        if f_ini_str:
            try:
                f_ini = datetime.strptime(str(f_ini_str).split()[0], "%Y-%m-%d").date()
                dias_transcurridos = (hoy - f_ini).days
                dias_transcurridos = max(0, dias_transcurridos)
                ganancia_dep = capital * (tae * (dias_transcurridos / 365.0))
            except Exception:
                pass
        val = capital + ganancia_dep
        inv = capital
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
st.title("💰 Copiloto Financiero & Multicuenta")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Capital Total", f"{capital_total:,.2f} €")
m2.metric("Efectivo Libre (Cuentas)", f"{efectivo_disponible:,.2f} €")
m3.metric("Valor Inversiones / Ahorro", f"{valor_portafolio_actual:,.2f} €")
ganancia_portafolio = valor_portafolio_actual - total_invertido
m4.metric("Rendimiento Inversiones", f"{ganancia_portafolio:+,.2f} €")

st.divider()

# --- PESTAÑAS DE NAVEGACIÓN ---
tab_cuenta, tab_gastos, tab_inversiones, tab_ia = st.tabs([
    "🏦 Mis Cuentas Bancarias", "⚡ Gastos e Ingresos", "📈 Inversiones y Cuentas Remuneradas", "🤖 Asesor IA Ejecutor"
])

# ==========================================
# 1. CUENTAS BANCARIAS
# ==========================================
with tab_cuenta:
    st.subheader("🏦 Estado de tus Cuentas Bancarias")
    col_c1, col_c2, col_c3 = st.columns(3)
    
    with col_c1:
        st.markdown("### 💼 Cuenta Nómina")
        val_nom = st.number_input("Saldo Cuenta Nómina (€):", value=saldos_cuentas.get("Cuenta Nómina", 0.0), min_value=0.0, step=50.0, key="in_nomina")
        if st.button("Guardar Nómina", use_container_width=True):
            actualizar_saldo_cuenta("Cuenta Nómina", val_nom)
            st.rerun()
            
    with col_c2:
        st.markdown("### 🍊 Cuenta Naranja")
        val_nar = st.number_input("Saldo Cuenta Naranja (€):", value=saldos_cuentas.get("Cuenta Naranja", 0.0), min_value=0.0, step=50.0, key="in_naranja")
        if st.button("Guardar Naranja", use_container_width=True):
            actualizar_saldo_cuenta("Cuenta Naranja", val_nar)
            st.rerun()
            
    with col_c3:
        st.markdown("### 🟢 Trade Republic")
        val_tr = st.number_input("Saldo Trade Republic (€):", value=saldos_cuentas.get("Trade Republic", 0.0), min_value=0.0, step=50.0, key="in_tr")
        if st.button("Guardar Trade Republic", use_container_width=True):
            actualizar_saldo_cuenta("Trade Republic", val_tr)
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
    transacciones_visibles = [t for t in transacciones if not t.get("tipo", "").startswith("Config")]
    if transacciones_visibles:
        df_trans = pd.DataFrame(transacciones_visibles)
        columnas_mostrar = [c for c in ["id", "created_at", "concepto", "monto", "tipo"] if c in df_trans.columns]
        st.dataframe(df_trans[columnas_mostrar], use_container_width=True)
    else:
        st.info("No hay gastos ni ingresos registrados.")

# ==========================================
# 3. INVERSIONES Y CUENTAS REMUNERADAS
# ==========================================
with tab_inversiones:
    st.subheader("🏢 Inversiones, Fondos y Cuentas Remuneradas")
    
    opcion_carga = st.selectbox("Método de incorporación:", ["➕ Añadir Individualmente", "📁 Importación Masiva (Excel / CSV)"])
    st.divider()
    
    if opcion_carga == "📁 Importación Masiva (Excel / CSV)":
        st.markdown("### 📥 Sube tu cartera de golpe")
        df_plantilla = pd.DataFrame([
            {"tipo_activo": "Acción/ETF", "ticker": "AAPL", "nombre": "Apple Inc.", "acciones": 10.0, "precio_compra": 150.0, "interes_tae": 0.0},
            {"tipo_activo": "Cuenta Remunerada", "ticker": "TR", "nombre": "Efectivo Trade Republic", "acciones": 3000.0, "precio_compra": 1.0, "interes_tae": 3.04},
            {"tipo_activo": "Fondo Indexado", "ticker": "IE00B4L5Y983", "nombre": "Vanguard Global Stock", "acciones": 25.5, "precio_compra": 110.0, "interes_tae": 0.0}
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
                
                if st.button("🚀 Procesar e Insertar en Supabase", type="primary"):
                    for _, row in df_subida.iterrows():
                        agregar_activo_db(
                            ticker=str(row.get("ticker", "MANUAL")),
                            nombre=str(row.get("nombre", "Activo")),
                            acciones=float(row.get("acciones", 0)),
                            precio_compra=float(row.get("precio_compra", 0)),
                            tipo_activo=str(row.get("tipo_activo", "Acción/ETF")),
                            interes_tae=float(row.get("interes_tae", 0.0))
                        )
                    st.success("¡Importación masiva completada con éxito!")
                    st.rerun()
            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")

    else:
        tipo_seleccionado = st.radio("Tipo de activo o cuenta:", ["Acción / ETF", "Fondo Indexado", "Cuenta Remunerada / Depósito"], horizontal=True)
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
                    f_ticker_final = dict_f[sel_f]["symbol"] if 'sel_f' in locals() else "FONDO_MANUAL"
                    
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
            cr_nombre = st.text_input("Nombre (ej. Depósito Bancario):", value="Depósito Bancario")
            cr_capital = st.number_input("Capital Depositado (€):", min_value=0.0, value=1000.0)
            cr_tae = st.number_input("Interés Anual (% TAE):", min_value=0.0, value=3.0)
            f_inicio = st.date_input("Fecha Inicio de Depósito:", value=date.today())
                
            if st.button("Añadir Depósito / Cuenta Remunerada", use_container_width=True):
                agregar_activo_db("DEPOSITO", cr_nombre, cr_capital, 1.0, "Cuenta Remunerada", fecha_inicio=f_inicio, interes_tae=cr_tae)
                st.success("Depósito añadido correctamente.")
                st.rerun()

    st.divider()
    st.subheader("📋 Detalle y Gestión de Activos")
    
    if activos:
        tabla = []
        for item in activos:
            act_id = item.get("id")
            p_compra = float(item.get("precio_compra", 0))
            acciones = float(item.get("acciones", 0))
            ticker = item.get("ticker", "")
            nombre = item.get("nombre", ticker)
            tipo_act = item.get("tipo_activo", "Acción/ETF")
            
            if tipo_act in ["Depósito", "Cuenta Remunerada"]:
                capital = acciones
                tae = float(item.get("interes_tae", 0.0)) / 100.0
                f_ini_str = item.get("fecha_inicio")
                
                ganancia_dep = 0.0
                if f_ini_str:
                    try:
                        f_ini = datetime.strptime(str(f_ini_str).split()[0], "%Y-%m-%d").date()
                        dias_transcurridos = (hoy - f_ini).days
                        dias_transcurridos = max(0, dias_transcurridos)
                        ganancia_dep = capital * (tae * (dias_transcurridos / 365.0))
                    except Exception:
                        pass
                inv = capital
                val = capital + ganancia_dep
                gan = ganancia_dep
            elif tipo_act == "Fondo Indexado":
                p_actual = obtener_precio_eur(ticker) if ticker and ticker != "FONDO_MANUAL" else p_compra
                inv = acciones * p_compra
                val = acciones * p_actual
                gan = val - inv
            else:
                p_actual = obtener_precio_eur(ticker) or p_compra
                inv = acciones * p_compra
                val = acciones * p_actual
                gan = val - inv
                
            txt_rent = f"{gan:+.2f} €"
            color_estilo = "color: #2e7d32; font-weight: bold;" if gan >= 0 else "color: #c62828; font-weight: bold;"
            rentabilidad_html = f'<span style="{color_estilo}">{txt_rent}</span>'
            
            tabla.append({
                "id": act_id,
                "Tipo": tipo_act,
                "Activo": nombre,
                "Invertido (€)": f"{inv:,.2f}",
                "Valor Actual (€)": f"{val:,.2f}",
                "Ganancia": rentabilidad_html
            })
            
        df_tabla = pd.DataFrame(tabla)
        st.markdown(df_tabla.drop(columns=["id"]).to_html(escape=False, index=False), unsafe_allow_html=True)
        
        st.write("")
        st.markdown("### 🗑️ Eliminar Activo Erróneo")
        opciones_eliminar = {f"{row['Tipo']} - {row['Activo']} (ID: {row['id']})": row['id'] for row in tabla}
        sel_eliminar = st.selectbox("Selecciona activo a borrar si está mal introducido:", list(opciones_eliminar.keys()))
        if st.button("❌ Borrar Activo Seleccionado", type="primary"):
            eliminar_activo_db(opciones_eliminar[sel_eliminar])
            st.rerun()
    else:
        st.info("No hay inversiones ni cuentas remuneradas añadidas.")

# ==========================================
# 4. ASESOR IA EJECUTOR MULTICUENTA
# ==========================================
with tab_ia:
    st.subheader("🤖 Asistente IA Multicuenta Inteligente")
    st.caption("Escribe de forma natural indicando si es un depósito, cuenta remunerada o acción/ETF con su TAE y fecha.")
    
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    instruccion = st.text_area("Cuéntale a la IA tu inversión o depósito:", placeholder="Ejemplo: Añade un depósito de 1239.54 euros llamado Depósito Bancario 4 Meses con un TAE del 3% iniciado el 2026-01-01. Y también 10 acciones de S&P 500 compradas a 163.10 euros.")
    
    if st.button("Ejecutar con IA", use_container_width=True) and instruccion:
        if not api_key:
            st.error("Configura tu GEMINI_API_KEY en Secrets.")
        else:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                
                prompt_ia = f"""
                Eres el motor experto financiero de una app. Analiza detalladamente la petición del usuario: '{instruccion}'.
                
                Clasifica correctamente cada elemento:
                - Si es un depósito, cuenta remunerada o ahorros a plazo con TAE, usa tipo_activo: "Cuenta Remunerada", pon el capital como "acciones" (ej: 1239.54), precio_compra: 1.0, introduce la fecha de inicio ("fecha_inicio" en formato YYYY-MM-DD o la fecha actual si no se especifica) y el "interes_tae".
                - Si es una acción o ETF (como S&P 500, Apple, etc.), usa tipo_activo: "Acción/ETF", el número de acciones en "acciones", el precio unitario de compra en "precio_compra" y ticker si lo conoces (o "MANUAL").
                
                Responde ÚNICAMENTE con un JSON puro (sin bloques de código markdown) con esta estructura exacta:
                {{
                  "accion": "inversion",
                  "items": [
                    {{
                      "tipo_activo": "Cuenta Remunerada" o "Acción/ETF" o "Fondo Indexado",
                      "ticker": "...",
                      "nombre": "...",
                      "acciones": 0.0,
                      "precio_compra": 0.0,
                      "fecha_inicio": "YYYY-MM-DD o null",
                      "interes_tae": 0.0
                    }}
                  ]
                }}
                """
                
                # Lista masiva de respaldo con 5 modelos alternativos en cadena para evitar colapsos 503
                modelos_a_probar = [
                    "gemini-2.5-flash",
                    "gemini-2.0-flash",
                    "gemini-1.5-flash",
                    "gemini-2.5-pro",
                    "gemini-1.5-pro"
                ]
                
                res = None
                ultimo_error = None
                
                for mod in modelos_a_probar:
                    try:
                        res = client.models.generate_content(
                            model=mod,
                            contents=prompt_ia
                        )
                        break  # Si encuentra un modelo libre, sale del bucle con éxito
                    except Exception as err:
                        ultimo_error = err
                        continue
                
                if res is None:
                    raise Exception(f"Todos los servidores de IA están saturados en este momento. Detalle: {ultimo_error}")
                
                texto_limpio = res.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(texto_limpio)
                
                if data.get("accion") == "inversion":
                    items = data.get("items", [])
                    for it in items:
                        agregar_activo_db(
                            ticker=it.get("ticker", "MANUAL"),
                            nombre=it.get("nombre", "Activo"),
                            acciones=float(it.get("acciones", 0)),
                            precio_compra=float(it.get("precio_compra", 1.0)),
                            tipo_activo=it.get("tipo_activo", "Acción/ETF"),
                            fecha_inicio=it.get("fecha_inicio"),
                            interes_tae=float(it.get("interes_tae", 0.0))
                        )
                    st.success(f"¡IA: Se han añadido {len(items)} elementos correctamente!")
                else:
                    st.info("Instrucción procesada.")
                    
                st.rerun()
            except Exception as e:
                st.error(f"Error procesando con IA: {e}")
