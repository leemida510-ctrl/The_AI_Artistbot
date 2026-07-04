import os
import logging
import io
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode

# ===== CONFIGURATION =====
BOT_TOKEN = os.environ.get('BOT_TOKEN')
HF_API_KEY = os.environ.get('HF_API_KEY')
PORT = int(os.environ.get('PORT', 8080))
RAILWAY_URL = os.environ.get('RAILWAY_STATIC_URL', '')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")
if not HF_API_KEY:
    raise ValueError("HF_API_KEY environment variable is required!")
if not RAILWAY_URL:
    logging.warning("RAILWAY_STATIC_URL not set. Webhook may not work properly.")

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
        "prompt": "photorealistic, detailed, 8k, high quality, professional photography",
        "negative": "cartoon, anime, painting, sketch, blurry, low quality"
    },
    "anime": {
        "name": "🎌 Anime",
        "prompt": "anime style, studio ghibli, vibrant colors, detailed, beautiful artwork",
        "negative": "realistic, photorealistic, photograph, 3d render"
    },
    "painting": {
        "name": "🎨 Oil Painting",
        "prompt": "oil painting, artistic, brush strokes, masterpiece, van gogh style",
        "negative": "photorealistic, digital art, cartoon"
    },
    "cartoon": {
        "name": "🖍️ Cartoon",
        "prompt": "cartoon style, pixar, colorful, cheerful, animated, disney style",
        "negative": "realistic, photograph, dark, scary"
    },
    "sketch": {
        "name": "✏️ Sketch",
        "prompt": "pencil sketch, detailed shading, black and white, artistic drawing",
        "negative": "color, painting, photorealistic, digital art"
    },
    "cyberpunk": {
        "name": "🌃 Cyberpunk",
        "prompt": "cyberpunk, neon lights, futuristic, dark atmosphere, synthwave, sci-fi",
        "negative": "nature, bright, daytime, vintage"
    },
    "fantasy": {
        "name": "🐉 Fantasy",
        "prompt": "fantasy art, magical, mythical creatures, epic, enchanting, mystical",
        "negative": "modern, realistic, technology, mundane"
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
    
    # Build full prompt with style
    if prompt.strip():
        full_prompt = f"{prompt}, {style_data['prompt']}"
    else:
        full_prompt = style_data['prompt']
    
    # Prepare API request
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": full_prompt[:1000],  # Limit prompt length
        "parameters": {
            "negative_prompt": style_data['negative'],
            "num_inference_steps": 30,
            "guidance_scale": 7.5,
            "width": 512,
            "height": 512
        }
    }
    
    try:
        logger.info(f"Generating image with style: {style}")
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
            # Model is loading - wait and retry
            logger.warning("Model is loading, waiting 5 seconds...")
            time.sleep(5)
            response = requests.post(
                f"https://api-inference.huggingface.co/models/{HF_MODEL}",
                headers=headers,
                json=payload,
                timeout=60
            )
            if response.status_code == 200:
                logger.info("Image generated successfully on retry")
                return response.content
        else:
            logger.error(f"API Error: {response.status_code} - {response.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("API request timed out")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return None

def check_cooldown(user_id: int) -> tuple[bool, int]:
    """Check if user is on cooldown"""
    if user_id in user_cooldown:
        elapsed = (datetime.now() - user_cooldown[user_id]).total_seconds()
        if elapsed < COOLDOWN_SECONDS:
            return False, int(COOLDOWN_SECONDS - elapsed)
    return True, 0

# ===== COMMAND HANDLERS =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    welcome_text = (
        "🎨 *Welcome to AI Artist Bot!*\n\n"
        "I transform your words into stunning AI-generated images.\n\n"
        "✨ *How to use:*\n"
        "• Simply type any description to generate an image\n"
        "• Use `/style` to change the art style\n"
        "• Use `/help` for all commands\n\n"
        "🚀 *Try this:* `a beautiful sunset over mountains`\n\n"
        "⚡ *Note:* Generation takes 10-30 seconds"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎨 Change Style", callback_data="show_styles")],
        [InlineKeyboardButton("💡 Tips & Tricks", callback_data="show_tips")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    help_text = (
        "🤖 *AI Artist Bot Commands*\n\n"
        "• `/start` - Welcome message\n"
        "• `/help` - Show this help\n"
        "• `/style` - Change art style\n"
        "• `/styles` - List all styles\n"
        "• `/info` - Bot information\n"
        "• `/reset` - Reset to default settings\n\n"
        "💡 *Just type any description to generate an image!*\n\n"
        "📝 *Example prompts:*\n"
        "• `a cat wearing a suit`\n"
        "• `futuristic city at night`\n"
        "• `a magical forest with glowing mushrooms`"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /style command"""
    user_id = update.effective_user.id
    current_style = user_styles.get(user_id, "realistic")
    current_name = STYLES[current_style]["name"]
    
    keyboard = []
    row = []
    for style_key, style_data in STYLES.items():
        button = InlineKeyboardButton(
            f"{'✅ ' if style_key == current_style else ''}{style_data['name']}",
            callback_data=f"style_{style_key}"
        )
        row.append(button)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎨 *Current Style:* {STYLES[current_style]['name']}\n\n"
        f"Select a new style:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def styles_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /styles command"""
    styles_text = "🎨 *Available Art Styles*\n\n"
    for style_key, style_data in STYLES.items():
        styles_text += f"• {style_data['name']}\n"
        styles_text += f"  _{style_data['prompt'][:50]}..._\n\n"
    
    await update.message.reply_text(
        styles_text,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /info command"""
    info_text = (
        "ℹ️ *Bot Information*\n\n"
        "🤖 *Name:* AI Artist Bot\n"
        "🧠 *Model:* Stable Diffusion 2.1\n"
        "⚡ *Platform:* Railway\n"
        "🎨 *Styles:* 7 art styles available\n"
        "🆓 *Price:* Completely free\n"
        "⏱️ *Generation time:* 10-30 seconds\n\n"
        "📊 *Statistics:*\n"
        "• Active users: *Active* 🟢\n"
        "• Uptime: *99.9%* ✅\n\n"
        "👨‍💻 *Developer:* Open Source\n"
        "🔗 *Source:* GitHub"
    )
    await update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reset command"""
    user_id = update.effective_user.id
    if user_id in user_styles:
        del user_styles[user_id]
    await update.message.reply_text(
        "✅ *Reset successful!*\n\n"
        "Your style has been reset to *Realistic*.",
        parse_mode=ParseMode.MARKDOWN
    )

# ===== CALLBACK QUERY HANDLERS =====
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data == "show_styles":
        # Show style menu
        current_style = user_styles.get(user_id, "realistic")
        keyboard = []
        row = []
        for style_key, style_data in STYLES.items():
            button = InlineKeyboardButton(
                f"{'✅ ' if style_key == current_style else ''}{style_data['name']}",
                callback_data=f"style_{style_key}"
            )
            row.append(button)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"🎨 *Current Style:* {STYLES[current_style]['name']}\n\nSelect a new style:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return
    
    elif data == "show_tips":
        tips_text = (
            "💡 *Tips for Better Images*\n\n"
            "1. Be specific about what you want\n"
            "2. Include colors, mood, and lighting\n"
            "3. Mention the environment or setting\n"
            "4. Add artistic terms (photorealistic, vibrant)\n"
            "5. Try different styles for the same prompt\n\n"
            "✨ *Good:*\n"
            "`A golden retriever playing in a sunny park, photorealistic, warm colors`\n\n"
            "❌ *Bad:*\n"
            "`dog`"
        )
        await query.edit_message_text(tips_text, parse_mode=ParseMode.MARKDOWN)
        return
    
    elif data.startswith("style_"):
        style_key = data.replace("style_", "")
        if style_key in STYLES:
            user_styles[user_id] = style_key
            await query.edit_message_text(
                f"✅ *Style changed!*\n\n"
                f"Now using: {STYLES[style_key]['name']}\n\n"
                f"Send any description to generate an image in this style.",
                parse_mode=ParseMode.MARKDOWN
            )

# ===== IMAGE GENERATION HANDLER =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages and generate images"""
    user_id = update.effective_user.id
    prompt = update.message.text
    
    # Validate prompt
    if len(prompt) > MAX_PROMPT_LENGTH:
        await update.message.reply_text(
            f"⚠️ Prompt is too long! Maximum {MAX_PROMPT_LENGTH} characters.\n"
            f"Your prompt: {len(prompt)} characters"
        )
        return
    
    # Check cooldown
    can_generate, wait_time = check_cooldown(user_id)
    if not can_generate:
        await update.message.reply_text(
            f"⏳ Please wait {wait_time} seconds before generating another image."
        )
        return
    
    # Get user's style
    style = user_styles.get(user_id, "realistic")
    style_name = STYLES[style]["name"]
    
    # Send processing message
    status_msg = await update.message.reply_text(
        f"🎨 *Generating your image...*\n"
        f"🖌️ Style: {style_name}\n"
        f"⏱️ Estimated time: 10-30 seconds\n\n"
        f"📝 *Prompt:* _{prompt[:100]}{'...' if len(prompt) > 100 else ''}_",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Update cooldown
    user_cooldown[user_id] = datetime.now()
    
    try:
        # Generate image
        image_bytes = generate_image(prompt, style)
        
        if image_bytes:
            # Send the image
            caption = (
                f"🖼️ *Generated Image*\n"
                f"🎨 Style: {style_name}\n"
                f"📝 Prompt: `{prompt[:80]}{'...' if len(prompt) > 80 else ''}`\n\n"
                f"💡 Try `/style` to change styles or `/help` for commands"
            )
            
            await update.message.reply_photo(
                photo=io.BytesIO(image_bytes),
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Delete status message
            await status_msg.delete()
            
        else:
            await status_msg.edit_text(
                "❌ *Failed to generate image*\n\n"
                "Possible reasons:\n"
                "• The AI model is busy (try again)\n"
                "• Your prompt might be too complex\n"
                "• API limits reached (try later)\n\n"
                "💡 Try a simpler prompt or different style.",
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        logger.error(f"Error in handle_message: {str(e)}")
        await status_msg.edit_text(
            "❌ *An error occurred*\n\n"
            "Please try again later. If the problem persists, contact support.",
            parse_mode=ParseMode.MARKDOWN
        )

# ===== MAIN APPLICATION =====
def main() -> None:
    """Start the bot"""
    try:
        # Create application
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Add command handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("style", style_command))
        app.add_handler(CommandHandler("styles", styles_command))
        app.add_handler(CommandHandler("info", info_command))
        app.add_handler(CommandHandler("reset", reset_command))
        
        # Add message handler (non-command text)
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        # Add callback handler for buttons
        app.add_handler(CallbackQueryHandler(button_callback))
        
        # Configure webhook if on Railway
        if RAILWAY_URL:
            webhook_url = f"https://{RAILWAY_URL}/{BOT_TOKEN}"
            logger.info(f"Setting webhook to: {webhook_url}")
            
            # Setup webhook
            app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=BOT_TOKEN,
                webhook_url=webhook_url
            )
        else:
            # Fallback to polling (for local development)
            logger.info("Running in polling mode (local development)")
            app.run_polling()
            
    except Exception as e:
        logger.error(f"Failed to start bot: {str(e)}")
        raise

if __name__ == "__main__":
    # Import time for retry delay
    import time
    main()
