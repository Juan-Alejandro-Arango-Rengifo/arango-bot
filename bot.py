from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)
import sqlite3
from datetime import datetime
import random
import os

# ---------------- CONFIG ----------------

TOKEN = os.getenv("TOKEN")  # usa variable de entorno en Railway
CANAL = -1003602118784
if not TOKEN:
    raise RuntimeError("❌ TOKEN no encontrado en variables de entorno")


# ---------------- BASE DE DATOS (SQLite) ----------------

conn = sqlite3.connect("arango.db", check_same_thread=False)
cursor = conn.cursor()

# Tabla de domicilios
cursor.execute("""
CREATE TABLE IF NOT EXISTS domicilios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recogida TEXT,
    entrega TEXT,
    precio INTEGER,
    estado TEXT,
    restaurante_chat INTEGER,
    domiciliario_id INTEGER,
    codigo TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Tabla de domiciliarios (historial)
cursor.execute("""
CREATE TABLE IF NOT EXISTS domiciliarios (
    user_id INTEGER PRIMARY KEY,
    nombre TEXT,
    total_domicilios INTEGER DEFAULT 0
)
""")

conn.commit()

# ---------------- COMANDO START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    # 🔹 Viene desde el botón "Tomar domicilio"
    if args and args[0].startswith("tomar_"):
        try:
            did = int(args[0].split("_")[1])
        except:
            await update.message.reply_text("❌ Domicilio inválido")
            return

        cursor.execute(
            "SELECT estado, restaurante_chat FROM domicilios WHERE id = ?",
            (did,)
        )
        row = cursor.fetchone()

        if not row:
            await update.message.reply_text("❌ Este domicilio no existe")
            return

        estado, restaurante_chat = row

        if estado != "abierto":
            await update.message.reply_text(
                f"❌ El domicilio #{did} ya fue tomado o cerrado"
            )
            return

        codigo = f"AR{did}-{random.randint(100,999)}"

        cursor.execute("""
        UPDATE domicilios
        SET estado = ?, domiciliario_id = ?, codigo = ?
        WHERE id = ?
        """, (
            "tomado",
            update.effective_user.id,
            codigo,
            did
        ))
        conn.commit()

        # Confirmación al domiciliario
        await update.message.reply_text(
            f"✅ Domicilio #{did} asignado a ti\n\n"
            f"👤 Domiciliario: {update.effective_user.full_name}\n"
            f"🆔 Código de verificación: {codigo}"
        )

        # Botón marcar entregado (privado)
        boton_entregado = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Marcar como entregado",
                    callback_data=f"entregado_{did}"
                )
            ]
        ])

        await update.message.reply_text(
            "Cuando entregues el domicilio, presiona el botón:",
            reply_markup=boton_entregado
        )

        # Avisar al restaurante
        await context.bot.send_message(
            chat_id=restaurante_chat,
            text=(
                f"🛵 Domicilio #{did} tomado\n\n"
                f"👤 Domiciliario: {update.effective_user.full_name}\n"
                f"🆔 Código: {codigo}\n\n"
                f"⚠️ Entregar solo a quien diga este código"
            )
        )
        return

    # Inicio normal
    await update.message.reply_text(
        "👋 Bienvenido a AranGo\n\n"
        "/domicilio → Crear un nuevo domicilio"
    )

# ---------------- CREAR DOMICILIO ----------------

async def domicilio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["paso"] = "recogida"
    await update.message.reply_text("📍 Dirección de recogida:")

# ---------------- FLUJO DE MENSAJES ----------------

async def mensajes(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.user_data:
        return

    paso = context.user_data.get("paso")

    if paso == "recogida":
        context.user_data["recogida"] = update.message.text
        context.user_data["paso"] = "entrega"
        await update.message.reply_text("📍 Dirección de entrega:")

    elif paso == "entrega":
        context.user_data["entrega"] = update.message.text
        context.user_data["paso"] = "valor"
        await update.message.reply_text(
            "💰 Valor del domicilio (solo números)\nEjemplo: 7000"
        )

    elif paso == "valor":
        texto_valor = update.message.text.strip()

        if not texto_valor.isdigit():
            await update.message.reply_text(
                "❌ El valor del domicilio debe ser solo numérico.\n"
                "✅ Ingresa nuevamente un valor válido."
            )
            return

        recogida = context.user_data["recogida"]
        entrega = context.user_data["entrega"]
        valor = int(texto_valor)

        cursor.execute("""
        INSERT INTO domicilios
        (recogida, entrega, valor, estado, restaurante_chat, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            recogida,
            entrega,
            valor,
            "abierto",
            update.effective_chat.id,
            datetime.now().isoformat()
        ))
        conn.commit()

        domicilio_id = cursor.lastrowid

        mensaje = (
            f"🛵 DOMICILIO #{domicilio_id} – AranGo\n"
            f"📍 {recogida} → {entrega}\n"
            f"💰 {valor}"
        )

        boton = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🚀 Tomar domicilio",
                    url=f"https://t.me/AranGoDelivery_bot?start=tomar_{domicilio_id}"
                )
            ]
        ])

        await context.bot.send_message(
            chat_id=CANAL,
            text=mensaje,
            reply_markup=boton
        )

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Domicilio #{domicilio_id} publicado correctamente"
        )

# ---------------- MARCAR COMO ENTREGADO ----------------

async def marcar_entregado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    did = int(query.data.split("_")[1])
    user_id = query.from_user.id

    cursor.execute("""
    SELECT estado, domiciliario_id, restaurante_chat
    FROM domicilios
    WHERE id = ?
    """, (did,))
    row = cursor.fetchone()

    if not row:
        await query.edit_message_text("❌ Domicilio no encontrado")
        return

    estado, domiciliario_id, restaurante_chat = row

    if estado != "tomado":
        await query.edit_message_text("❌ Este domicilio no puede marcarse como entregado")
        return

    if domiciliario_id != user_id:
        await query.edit_message_text("❌ No estás autorizado para cerrar este domicilio")
        return

    cursor.execute(
        "UPDATE domicilios SET estado = 'entregado' WHERE id = ?",
        (did,)
    )
    conn.commit()

    await query.edit_message_text(
        f"✅ Domicilio #{did} marcado como ENTREGADO"
    )

    await context.bot.send_message(
        chat_id=restaurante_chat,
        text=f"📦 Domicilio #{did} entregado correctamente. ¡Gracias por usar AranGo!"
    )

# ---------------- MAIN ----------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("domicilio", domicilio))
    app.add_handler(CallbackQueryHandler(marcar_entregado, pattern=r"^entregado_\d+"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensajes))

    print("🤖 Bot AranGo (DOMICILIOS) en ejecución...")
    app.run_polling()

if __name__ == "__main__":
    main()


