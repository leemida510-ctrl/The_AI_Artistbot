import os
import logging
import io
import time
from datetime import datetime
from typing import Optional, Dict
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode

# ===== CONFIGURATION =====
BOT_TOKEN = os.environ.get('BOT_TOKEN')
HF_API_KEY = os.environ.get('HF_API_KEY')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")
if not HF_API_KEY:
    raise ValueError("HF_API_KEY environment variable is required!")

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== CONSTANTS =====
HF_MODEL = "stabilityai/stable-diffusion-2-1"
COOLDOWN_SECONDS = 10
MAX_PROMPT_LENGTH = 500

# ===== AVAILABLE STYLES =====
STYLES = {
    "realistic": {
        "name": "📸 Realistic",
        "prompt": "photorealistic, detailed, 8k, high quality"
    },
    "anime": {
        "name": "🎌 Anime",
        "prompt": "anime style, studio ghibli, vibrant colors, detailed"
    },
    "painting": {
        "name": "🎨 Oil Painting",
        "prompt": "oil painting, artistic, brush strokes, masterpiece"
    },
    "cartoon": {
        "name": "🖍️ Cartoon",
        "prompt": "cartoon style, pixar, colorful, cheerful, animated"
    },
    "sketch": {
        "name": "✏️ Sketch",
        "prompt": "pencil sketch, detailed shading, black and white"
    },
    "cyberpunk": {
        "name": "🌃 Cyberpunk",
        "prompt": "cyberpunk, neon lights, futuristic, dark atmosphere"
    },
    "fantasy": {
        "name": "🐉 Fantasy",
        "prompt": "fantasy art, magical, mythical creatures, epic"
    }
}

# ===== USER DATA =====
user_styles: Dict[int, str] = {}
user_cooldown: Dict[int, datetime] = {}

# ===== HELPER FUNCTIONS =====
def generate_image(prompt: str, style: str = "realistic") -> Optional[bytes]:
    """Generate image using Hugging Face API"""
    if style not in STYLES:
        style = "realistic"
    
    style_data = STYLES[style]
    
    if prompt.strip():
        full_prompt = f"{prompt}, {style_data['prompt']}"
    else:
        full_prompt = style_data['prompt']
    
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": full_prompt[:1000],
        "parameters": {
            "negative_prompt": "blurry, low quality, distorted, ugly",
            "num_inference_steps": 20,
            "guidance_scale": 7.0
        }
    }
    
    try:
        logger.info(f"Generating image...")
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{HF_MODEL}",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            logger.info("Image generated successfully")
            return response.content
        elif response.status_code == 503:
            logger.warning("Model loading, waiting...")
            time.sleep(10)
            response = requests.post(
                f"https://api-inference.huggingface.co/models/{HF_MODEL}",
                headers=headers,
                json=payload,
                timeout=60
            )
            if response.status_code == 200:
                return response.content
        else:
            logger.error(f"API Error: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return None

def check_cooldown(user_id: int) -> tuple[bool, int]:
    if user_id in user_cooldown:
        elapsed = (datetime.now() - user_cooldown[user_id]).total_seconds()
        if elapsed < COOLDOWN_SECONDS:
            return False, int(COOLDOWN_SECONDS - elapsed)
    return True, 0

# ===== COMMAND HANDLERS =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🎨 Style", callback_data="show_styles")],
        [InlineKeyboardButton("💡 Tips", callback_data="show_tips")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎨 *Welcome to AI Artist Bot!*\n\n"
        "Send any description to generate an AI image.\n"
        "Use /style to change art style.\n\n"
        "Example: `a beautiful sunset over mountains`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 *Commands:*\n"
        "/start - Welcome\n"
        "/help - This help\n"
        "/style - Change style\n"
        "/styles - List styles\n"
        "/reset - Reset to default\n\n"
        "Just type any description to generate an image!",
        parse_mode=ParseMode.MARKDOWN
    )

async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    current = user_styles.get(user_id, "realistic")
    
    keyboard = []
    row = []
    for key, data in STYLES.items():
        btn = InlineKeyboardButton(
            f"{'✅ ' if key == current else ''}{data['name']}",
            callback_data=f"style_{key}"
        )
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    await update.message.reply_text(
        f"Current: {STYLES[current]['name']}\nSelect a style:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def styles_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "🎨 *Styles:*\n\n"
    for key, data in STYLES.items():
        text += f"• {data['name']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id in user_styles:
        del user_styles[user_id]
    await update.message.reply_text("✅ Reset to Realistic style!")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "show_styles":
        await style_command(update, context)
        return
    
    if data == "show_tips":
        await query.edit_message_text(
            "💡 *Tips:*\n\n"
            "• Be specific in descriptions\n"
            "• Use colors, mood, lighting\n"
            "• Add artistic terms\n"
            "• Try different styles\n\n"
            "✨ Good: `A golden retriever in a sunny park, photorealistic`\n"
            "❌ Bad: `dog`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if data.startswith("style_"):
        style = data.replace("style_", "")
        user_styles[update.effective_user.id] = style
        await query.edit_message_text(
            f"✅ Style changed to: {STYLES[style]['name']}\n\n"
            "Send a description to generate an image!",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    prompt = update.message.text
    
    if len(prompt) > MAX_PROMPT_LENGTH:
        await update.message.reply_text(f"⚠️ Too long! Max {MAX_PROMPT_LENGTH} characters.")
        return
    
    can_generate, wait_time = check_cooldown(user_id)
    if not can_generate:
        await update.message.reply_text(f"⏳ Wait {wait_time}s...")
        return
    
    style = user_styles.get(user_id, "realistic")
    style_name = STYLES[style]["name"]
    
    status = await update.message.reply_text(
        f"🎨 Generating...\nStyle: {style_name}\n⏱️ 10-30 seconds",
        parse_mode=ParseMode.MARKDOWN
    )
    
    user_cooldown[user_id] = datetime.now()
    
    try:
        image_bytes = generate_image(prompt, style)
        
        if image_bytes:
            await update.message.reply_photo(
                photo=io.BytesIO(image_bytes),
                caption=f"🎨 {style_name}\n📝 {prompt[:80]}{'...' if len(prompt) > 80 else ''}",
                parse_mode=ParseMode.MARKDOWN
            )
            await status.delete()
        else:
            await status.edit_text(
                "❌ Failed to generate image.\n"
                "Try again or use a simpler prompt."
            )
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await status.edit_text("❌ Error occurred. Please try again.")

# ===== MAIN =====
def main():
    try:
        logger.info("Starting bot...")
        app = Application.builder().token(BOT_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("style", style_command))
        app.add_handler(CommandHandler("styles", styles_command))
        app.add_handler(CommandHandler("reset", reset_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(CallbackQueryHandler(button_callback))
        
        logger.info("Bot is running with polling...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Crashed: {str(e)}")
            logger.info("Restarting in 5 seconds...")
            time.sleep(5)
