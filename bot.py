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
import random

TOKEN = "8140604222:AAHccwCMbjtmJdLh16BFYxmqCmS438lfzRc"
CANAL = -1003602118784

# 🔢 contador y almacenamiento en memoria
pedido_id = 0
pedidos = {}

# ---------------- COMANDO START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    # 🔹 Viene desde el botón "Tomar pedido"
    if args and args[0].startswith("tomar_"):
        try:
            pid = int(args[0].split("_")[1])
        except:
            await update.message.reply_text("❌ Pedido inválido")
            return

        if pid not in pedidos:
            await update.message.reply_text("❌ Este pedido no existe")
            return

        if pedidos[pid]["estado"] != "abierto":
            await update.message.reply_text(
                f"❌ El pedido #{pid} ya fue tomado o cerrado"
            )
            return

        codigo = f"AR{pid}-{random.randint(100,999)}"

        pedidos[pid]["estado"] = "tomado"
        pedidos[pid]["tomado_por"] = update.effective_user.id
        pedidos[pid]["codigo"] = codigo

        # Confirmación al domiciliario
        await update.message.reply_text(
            f"✅ Pedido #{pid} asignado a ti\n\n"
            f"👤 Nombre: {update.effective_user.full_name}\n"
            f"🆔 Código de verificación: {codigo}"
        )

        # 🔘 Botón marcar entregado (PRIVADO)
        boton_entregado = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Marcar como entregado",
                    callback_data=f"entregado_{pid}"
                )
            ]
        ])

        await update.message.reply_text(
            "Cuando entregues el pedido, presiona el botón:",
            reply_markup=boton_entregado
        )

        # Avisar al restaurante
        await context.bot.send_message(
            chat_id=pedidos[pid]["restaurante_chat"],
            text=(
                f"🛵 Pedido #{pid} tomado\n\n"
                f"👤 Domiciliario: {update.effective_user.full_name}\n"
                f"🆔 Código: {codigo}\n\n"
                f"⚠️ Entregar solo a quien diga este código"
            )
        )
        return

    # Inicio normal
    await update.message.reply_text(
        "👋 Bienvenido a AranGo\n\n"
        "/pedido → Crear un nuevo pedido"
    )

# ---------------- CREAR PEDIDO ----------------

async def pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["paso"] = "recogida"
    await update.message.reply_text("📍 Dirección de recogida:")

# ---------------- FLUJO DE MENSAJES ----------------

async def mensajes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pedido_id

    if not context.user_data:
        return

    paso = context.user_data.get("paso")

    if paso == "recogida":
        context.user_data["recogida"] = update.message.text
        context.user_data["paso"] = "entrega"
        await update.message.reply_text("📍 Dirección de entrega:")

    elif paso == "entrega":
        context.user_data["entrega"] = update.message.text
        context.user_data["paso"] = "precio"
        await update.message.reply_text("💰 Valor del domicilio:")

    elif paso == "precio":
        texto_precio = update.message.text.strip()

        # ❌ Validación numérica
        if not texto_precio.isdigit():
            await update.message.reply_text(
                "❌ El valor del domicilio debe ser solo numérico.\n"
                "✅ Ingrese nuevamente un valor válido."
            )
            return

        recogida = context.user_data["recogida"]
        entrega = context.user_data["entrega"]
        precio = texto_precio

        pedido_id += 1

        pedidos[pedido_id] = {
            "estado": "abierto",
            "tomado_por": None,
            "codigo": None,
            "restaurante_chat": update.effective_chat.id
        }

        mensaje = (
            f"🛵 PEDIDO #{pedido_id} – AranGo\n"
            f"📍 {recogida} → {entrega}\n"
            f"💰 {precio}"
        )

        boton = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🚀 Tomar pedido",
                    url=f"https://t.me/AranGoDelivery_bot?start=tomar_{pedido_id}"
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
            f"✅ Pedido #{pedido_id} publicado correctamente"
        )

# ---------------- MARCAR COMO ENTREGADO ----------------

async def marcar_entregado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pid = int(query.data.split("_")[1])
    user_id = query.from_user.id

    if pid not in pedidos:
        await query.edit_message_text("❌ Pedido no encontrado")
        return

    pedido = pedidos[pid]

    if pedido["estado"] != "tomado":
        await query.edit_message_text("❌ Este pedido no puede marcarse como entregado")
        return

    if pedido["tomado_por"] != user_id:
        await query.edit_message_text("❌ No estás autorizado para cerrar este pedido")
        return

    pedidos[pid]["estado"] = "entregado"

    await query.edit_message_text(
        f"✅ Pedido #{pid} marcado como ENTREGADO"
    )

    # Avisar al restaurante
    await context.bot.send_message(
        chat_id=pedido["restaurante_chat"],
        text=f"📦 Pedido #{pid} entregado correctamente. ¡Gracias por usar AranGo!"
    )

# ---------------- MAIN ----------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pedido", pedido))
    app.add_handler(CallbackQueryHandler(marcar_entregado, pattern=r"^entregado_\d+"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensajes))

    print("🤖 Bot AranGo en ejecución...")
    app.run_polling()

if __name__ == "__main__":
    main()
