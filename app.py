import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import json
from datetime import date
from supabase import create_client, Client
import io
import time

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

# --- BARRA LATERAL / CERRAR SESIÓN Y ZONA DE PELIGRO ---
with st.sidebar:
    st.write("👤 **Sesión Activa**")
    if st.button("🔒 Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()
    st.divider()
    
    st.markdown("### ⚠️ Zona de Peligro")
    if "confirmar_borrado_total" not in st.session_state:
        st.session_state.confirmar_borrado_total = False

    if not st.session_state.confirmar_borrado_total:
        if st.button("🗑️ Borrar Todos los Datos", type="secondary", use_container_width=True):
            st.session_state.confirmar_borrado_total = True
            st.rerun()
    else:
        st.error("¿Estás 100% seguro? Se borrarán todos los datos de la base de datos.")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("Sí, borrar todo", type="primary", use_container_width=True):
                try:
                    supabase.table("transacciones").delete().neq("id", 0).execute()
                    st.success("¡Base de datos restablecida por completo!")
                    st.session_state.confirmar_borrado_total = False
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al borrar los datos: {e}")
        with col_b2:
            if st.button("Cancelar", use_container_width=True):
                st.session_state.confirmar_borrado_total = False
                st.rerun()

# --- FUNCIONES DE BASE DE DATOS (TODO EN TRANSACCIONES) ---
def cargar_datos_brutos():
    try:
        res = supabase.table("transacciones").select("*").execute()
        return res.data or []
    except Exception:
        return []

def registrar_transaccion(concepto, monto, tipo, ticker="", extra_data=""):
    try:
        supabase.table("transacciones").insert({
            "concepto": str(concepto),
            "monto": float(monto),
            "tipo": str(tipo)
        }).execute()
    except Exception as e:
        st.error(f"Error al registrar en base de datos: {e}")

def eliminar_registro_db(reg_id):
    try:
        supabase.table("transacciones").delete().eq("id", reg_id).execute()
        st.success("Elemento eliminado correctamente.")
    except Exception as e:
        st.error(f"Error al eliminar: {e}")

def actualizar_monto_db(reg_id, nuevo_monto):
    try:
        supabase.table("transacciones").update({
            "monto": float(nuevo_monto)
        }).eq("id", reg_id).execute()
    except Exception as e:
        st.error(f"Error al actualizar en BD: {e}")

# --- MERCADO Y COTIZACIONES ---
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

@st.cache_data(ttl=600)
def obtener_precio_eur(ticker_code):
    if not ticker_code or ticker_code in ["MANUAL", "FONDO_MANUAL", "DEPOSITO", "CUENTA"]:
        return None
    try:
        stock = yf.Ticker(ticker_code)
        hist = stock.history(period="1d")
        if hist.empty:
            return None
        precio = float(hist['Close'].iloc[-1])
        try:
            currency = stock.fast_info.currency
            if currency and currency.upper() == "USD":
                fx = yf.Ticker("EURUSD=X").history(period="1d")
                if not fx.empty:
                    precio /= float(fx['Close'].iloc[-1])
        except Exception:
            pass
        return precio
    except Exception:
        return None

# --- CARGA Y SEPARACIÓN DE DATOS ---
datos_brutos = cargar_datos_brutos()

transacciones = [t for t in datos_brutos if t.get("tipo") in ["Ingreso", "Gasto"]]
saldos_cuentas_db = [t for t in datos_brutos if t.get("tipo") == "Config_Cuenta"]
activos = [t for t in datos_brutos if t.get("tipo") in ["Acción/ETF", "Fondo Indexado", "Cuenta Remunerada"]]

# Procesar saldos de cuentas
saldos_cuentas = {"Cuenta Nómina": 0.0, "Cuenta Naranja": 0.0, "Trade Republic": 0.0}
for t in saldos_cuentas_db:
    concepto = t.get("concepto")
    for cuenta in saldos_cuentas.keys():
        if cuenta in concepto:
            saldos_cuentas[cuenta] = float(t.get("monto", 0.0))

def actualizar_saldo_cuenta(nombre_cuenta, nuevo_monto):
    concepto_clave = f"SALDO_CUENTA_{nombre_cuenta}"
    try:
        supabase.table("transacciones").delete().eq("concepto", concepto_clave).execute()
        registrar_transaccion(concepto_clave, nuevo_monto, "Config_Cuenta")
        st.success(f"¡Saldo de '{nombre_cuenta}' actualizado correctamente!")
    except Exception as e:
        st.error(f"Error al actualizar saldo de {nombre_cuenta}: {e}")

# --- CÁLCULOS MÉTRICOS PRINCIPALES ---
total_ingresos = sum(t.get("monto", 0) for t in transacciones if t.get("tipo") == "Ingreso")
total_gastos = sum(t.get("monto", 0) for t in transacciones if t.get("tipo") == "Gasto")

efectivo_base_total = sum(saldos_cuentas.values())
efectivo_disponible = efectivo_base_total + total_ingresos - total_gastos

valor_portafolio_actual = 0.0
total_invertido = 0.0

for a in activos:
    # Usamos el campo monto para almacenar el valor actual o el precio de compra según convenga, 
    # o guardamos la estructura en el concepto. Para simplificar:
    # Guardamos en 'monto' el valor actual o guardaremos un diccionario serializado en concepto.
    pass # Los cálculos se detallan abajo en su pestaña correspondiente

# --- INTERFAZ / PANEL SUPERIOR ---
st.title("💰 Copiloto Financiero & Multicuenta")

# Recálculo rápido para métricas
val_portafolio = 0.0
inv_total = 0.0
for a in activos:
    try:
        partes = a.get("concepto", "").split("|||")
        # Formato concepto: Nombre | Acciones | PrecioCompra | ValorManual | TipoActivo
        if len(partes) >= 5:
            nombre = partes[0]
            acciones = float(partes[1])
            p_compra = float(partes[2])
            val_manual = float(partes[3])
            tipo_act = partes[4]
            ticker = a.get("monto", "MANUAL") # Usamos monto temporalmente o ticker
            
            # Re-evaluamos inversión y valor
            if tipo_act in ["Depósito", "Cuenta Remunerada"]:
                inv = acciones
                val = val_manual if val_manual > 0 else inv
            elif tipo_act == "Fondo Indexado":
                inv = p_compra
                val = val_manual if val_manual > 0 else inv
            else:
                inv = acciones * p_compra
                p_actual = obtener_precio_eur(ticker) if ticker and ticker not in ["MANUAL", "CUENTA"] else 0
                if p_actual and p_actual > 0:
                    val = acciones * p_actual
                else:
                    val = val_manual if val_manual > 0 else inv
            inv_total += inv
            val_portafolio += val
    except Exception:
        pass

capital_total = efectivo_disponible + val_portafolio

m1, m2, m3, m4 = st.columns(4)
m1.metric("Capital Total", f"{capital_total:,.2f} €")
m2.metric("Efectivo Libre (Cuentas)", f"{efectivo_disponible:,.2f} €")
m3.metric("Valor Inversiones / Ahorro", f"{val_portafolio:,.2f} €")
ganancia_portafolio = val_portafolio - inv_total
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
        registrar_transaccion(concepto, monto, tipo)
        st.success(f"Guardado: {concepto}")
        st.rerun()

    st.divider()
    st.subheader("📊 Historial de Transacciones")
    if transacciones:
        df_trans = pd.DataFrame(transacciones)
        columnas_mostrar = [c for c in ["id", "created_at", "concepto", "monto", "tipo"] if c in df_trans.columns]
        st.dataframe(df_trans[columnas_mostrar], use_container_width=True)
    else:
        st.info("No hay gastos ni ingresos registrados.")

# ==========================================
# 3. INVERSIONES Y CUENTAS REMUNERADAS
# ==========================================
with tab_inversiones:
    st.subheader("🏢 Inversiones, Fondos y Cuentas Remuneradas")
    
    tipo_seleccionado = st.radio("Tipo de activo o cuenta:", ["Acción / ETF", "Fondo Indexado", "Cuenta Remunerada / Depósito"], horizontal=True)
    st.write("")
    
    def agregar_activo_seguro(ticker, nombre, acciones, precio_compra, tipo_activo, valor_actual_manual=0.0):
        # Guardamos todo empaquetado en el campo concepto de la tabla transacciones para evitar alterar esquemas
        # Formato: Nombre ||| Acciones ||| PrecioCompra ||| ValorManual ||| TipoActivo
        payload = f"{nombre}|||{acciones}|||{precio_compra}|||{valor_actual_manual}|||{tipo_activo}"
        registrar_transaccion(payload, 0.0, tipo_activo)

    if tipo_seleccionado == "Acción / ETF":
        busqueda = st.text_input("Buscar Acción o ETF (ej: AVAV, VRT, VKTX):", value="AVAV")
        if busqueda:
            opciones = buscar_coincidencias(busqueda)
            if opciones:
                dict_opciones = {f"{item['name']} ({item['symbol']}) - {item['exchange']}": item for item in opciones}
                seleccion = st.selectbox("Selecciona activo:", list(dict_opciones.keys()))
                activo_elegido = dict_opciones[seleccion]
                
                c_acc, c_prec = st.columns(2)
                with c_acc:
                    num_acc = st.number_input("Nº Acciones:", min_value=0.000001, value=1.0, format="%.6f")
                with c_prec:
                    prec_c = st.number_input("Precio compra total (€):", min_value=0.0, value=100.0)
                    
                if st.button("Añadir Acción/ETF", use_container_width=True):
                    precio_unitario = prec_c / num_acc if num_acc > 0 else 0
                    agregar_activo_seguro(activo_elegido["symbol"], activo_elegido["name"], num_acc, precio_unitario, "Acción/ETF")
                    st.success("Acción añadida correctamente.")
                    st.rerun()

    elif tipo_seleccionado == "Fondo Indexado":
        f_nombre = st.text_input("Nombre del Fondo o ISIN:", value="Fondo S&P 500 (40068337561)")
        c_inv, c_act = st.columns(2)
        with c_inv:
            total_invertido_input = st.number_input("Total Invertido (€):", min_value=0.0, value=1631.09)
        with c_act:
            total_actual_input = st.number_input("Valor Actual Total (€):", min_value=0.0, value=1797.24)
            
        if st.button("Añadir Fondo Indexado", use_container_width=True):
            agregar_activo_seguro("40068337561", f_nombre, 1.0, total_invertido_input, "Fondo Indexado", valor_actual_manual=total_actual_input)
            st.success("Fondo indexado añadido correctamente.")
            st.rerun()

    else:
        cr_nombre = st.text_input("Nombre del Depósito:", value="Depósito bancario")
        cr_capital = st.number_input("Capital Depositado / Valor Actual (€):", min_value=0.0, value=1239.54)
            
        if st.button("Añadir Depósito / Cuenta Remunerada", use_container_width=True):
            agregar_activo_seguro("DEPOSITO", cr_nombre, cr_capital, 1.0, "Cuenta Remunerada", valor_actual_manual=cr_capital)
            st.success("Depósito añadido correctamente.")
            st.rerun()

    st.divider()
    st.subheader("📋 Detalle, Cotización y Edición de Activos")
    
    if activos:
        tabla = []
        for item in activos:
            act_id = item.get("id")
            partes = item.get("concepto", "").split("|||")
            if len(partes) < 5:
                continue
            nombre = partes[0]
            acciones = float(partes[1])
            p_compra = float(partes[2])
            val_manual = float(partes[3])
            tipo_act = partes[4]
            ticker = "MANUAL"
            
            if tipo_act in ["Depósito", "Cuenta Remunerada"]:
                inv = acciones
                val = val_manual if val_manual > 0 else inv
            elif tipo_act == "Fondo Indexado":
                inv = p_compra
                val = val_manual if val_manual > 0 else inv
            else:
                inv = acciones * p_compra
                p_actual = obtener_precio_eur(ticker) if ticker and ticker not in ["MANUAL", "CUENTA"] else 0
                if p_actual and p_actual > 0:
                    val = acciones * p_actual
                else:
                    val = val_manual if val_manual > 0 else inv
                
            gan = val - inv
            rent_pct = (gan / inv * 100) if inv > 0 else 0.0
            
            tabla.append({
                "id": act_id,
                "Tipo": tipo_act,
                "Activo": nombre,
                "Invertido (€)": round(inv, 2),
                "Valor Actual (€)": round(val, 2),
                "Ganancia (€)": round(gan, 2),
                "Rentabilidad (%)": round(rent_pct, 2),
                "datos_originales": partes
            })
            
        if tabla:
            df_tabla = pd.DataFrame(tabla)
            
            st.caption("💡 Puedes editar directamente el **Valor Actual (€)** de cualquier activo en la tabla y pulsar el botón inferior para guardarlo.")
            
            df_editado = st.data_editor(
                df_tabla,
                column_config={
                    "id": None,
                    "datos_originales": None,
                    "Tipo": st.column_config.TextColumn("Tipo", disabled=True),
                    "Activo": st.column_config.TextColumn("Activo", disabled=True),
                    "Invertido (€)": st.column_config.NumberColumn("Invertido (€)", format="%.2f €", disabled=True),
                    "Valor Actual (€)": st.column_config.NumberColumn("Valor Actual (€)", format="%.2f €"),
                    "Ganancia (€)": st.column_config.NumberColumn("Ganancia (€)", format="%.2f €", disabled=True),
                    "Rentabilidad (%)": st.column_config.NumberColumn("Rentabilidad (%)", format="%.2f %%", disabled=True)
                },
                hide_index=True,
                use_container_width=True,
                key="editor_activos"
            )
            
            if st.button("💾 Guardar Actualización de Valores en la BD", type="primary"):
                for _, row in df_editado.iterrows():
                    p = row["datos_originales"]
                    nuevo_val = row["Valor Actual (€)"]
                    # Reconstruir concepto actualizado
                    nuevo_concepto = f"{p[0]}|||{p[1]}|||{p[2]}|||{nuevo_val}|||{p[4]}"
                    try:
                        supabase.table("transacciones").update({"concepto": nuevo_concepto}).eq("id", row["id"]).execute()
                    except Exception:
                        pass
                st.success("¡Valores actualizados correctamente!")
                st.rerun()
                
            st.divider()
            st.markdown("### 🗑️ Eliminar Activo")
            opciones_eliminar = {f"{row['Tipo']} - {row['Activo']} (ID: {row['id']})": row['id'] for row in tabla}
            sel_eliminar = st.selectbox("Selecciona activo a borrar:", list(opciones_eliminar.keys()))
            if st.button("❌ Borrar Activo Seleccionado", type="primary"):
                eliminar_registro_db(opciones_eliminar[sel_eliminar])
                st.rerun()
    else:
        st.info("No hay inversiones ni cuentas remuneradas añadidas.")

# ==========================================
# 4. ASESOR IA EJECUTOR MULTICUENTA
# ==========================================
with tab_ia:
    st.subheader("🤖 Asistente IA Multicuenta Inteligente")
    st.caption("Pega la información completa de tus inversiones y la IA la estructurará sin equivocaciones.")
    
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    instruccion = st.text_area("Cuéntale a la IA tus inversiones:", placeholder="Ejemplo: Tengo 1631,09€ valorados en 1797,24€ en el fondo S&P 500...")
    
    if st.button("Ejecutar con IA", use_container_width=True) and instruccion:
        if not api_key:
            st.error("Configura tu GEMINI_API_KEY en Secrets.")
        else:
            try:
                from google import genai
                
                client = genai.Client(api_key=api_key)
                
                prompt_ia = f"""
                Eres un experto financiero analizando la frase del usuario: '{instruccion}'.
                Extrae cada activo mencionado estructurándolos rigurosamente. 
                Tipos de activos permitidos exactamente: "Acción/ETF", "Fondo Indexado", "Cuenta Remunerada".
                
                Para cada activo extrae:
                - "tipo_activo": "Acción/ETF", "Fondo Indexado" o "Cuenta Remunerada".
                - "nombre": Nombre descriptivo.
                - "acciones": Número de acciones (si es acción, pon la cantidad exacta como decimal; si es fondo pon 1.0; si es depósito pon el capital).
                - "precio_compra": Si es acción, pon el PRECIO TOTAL invertido en esa acción. Si es fondo, pon el CAPITAL INVERTIDO. Si es depósito, pon 1.0.
                - "valor_actual_manual": Si se indica un valor actual de mercado (como en el fondo o depósito), ponlo aquí. Si no, pon 0.0.
                
                Responde ÚNICAMENTE con un JSON puro (sin bloques de código markdown ```json) con esta estructura exacta:
                {{
                  "accion": "inversion",
                  "items": [
                    {{
                      "tipo_activo": "...",
                      "nombre": "...",
                      "acciones": 0.0,
                      "precio_compra": 0.0,
                      "valor_actual_manual": 0.0
                    }}
                  ]
                }}
                """
                
                modelos_a_probar = ["gemini-2.5-flash", "gemini-3.5-flash"]
                res = None
                ultimo_error = None
                inicio_proceso = time.time()
                
                with st.spinner("🤖 Procesando con IA con máxima precisión..."):
                    while (time.time() - inicio_proceso) < 30:
                        for mod in modelos_a_probar:
                            try:
                                res = client.models.generate_content(model=mod, contents=prompt_ia)
                                break
                            except Exception as err:
                                ultimo_error = err
                                continue
                        if res is not None:
                            break
                        time.sleep(2)
                
                if res is None:
                    raise Exception(f"Error de conexión con IA: {ultimo_error}")
                
                texto_limpio = res.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(texto_limpio)
                
                if data.get("accion") == "inversion":
                    items = data.get("items", [])
                    for it in items:
                        t_act = it.get("tipo_activo", "Acción/ETF")
                        acc = float(it.get("acciones", 1.0))
                        p_c = float(it.get("precio_compra", 0.0))
                        v_man = float(it.get("valor_actual_manual", 0.0))
                        
                        if t_act == "Acción/ETF" and acc > 0:
                            p_c = p_c / acc
                        
                        if t_act == "Cuenta Remunerada" and v_man == 0.0:
                            v_man = acc
                            
                        agregar_activo_seguro(
                            ticker="MANUAL",
                            nombre=it.get("nombre", "Activo IA"),
                            acciones=acc,
                            precio_compra=p_c,
                            tipo_activo=t_act,
                            valor_actual_manual=v_man
                        )
                    st.success(f"¡IA: Inversiones interpretadas y añadidas con éxito!")
                else:
                    st.info("Instrucción procesada.")
                    
                st.rerun()
            except Exception as e:
                st.error(f"Error procesando con IA: {e}")
